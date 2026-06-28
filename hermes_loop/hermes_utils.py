"""Hermes binary discovery, task type detection, delegation prompt building, and session spawning."""

import json
import os
import re
import shutil
import subprocess
import threading
import time

import concurrent.futures
import pty
import select
import urllib.request

from .config import TASK_PATTERNS
from .file_utils import _log, extract_json_from_output
from .error_utils import classify_error
from .validation import validate_json_output
from .heartbeat import (
    _heartbeat_path,
    _run_heartbeat_monitor,
    _kill_session,
    _cleanup_heartbeat_file,
)

# Regex for stripping ANSI escape codes, TUI control chars, and carriage returns
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\].*?\x07|\x1b\[[0-9]*[KJhlsu]|\r")


def _read_stderr_real_time(
    proc: subprocess.Popen,
    worker_tag: str,
) -> None:
    """Daemon thread: read stderr line-by-line and log ALL output.

    Hermes prints tool calls, thinking, model responses, and token info
    to stderr during ``chat -q`` sessions. This thread captures every line
    in real-time with a ``[STDERR{worker_tag}]`` prefix so the web UI
    can show per-worker hermes output live.
    """
    try:
        for raw_line in iter(proc.stderr.readline, ""):
            if not raw_line:
                break
            line = raw_line.rstrip("\n\r")
            if not line:
                continue
            # Log every line — tool calls, thinking, progress, everything
            _log(f"[STDERR{worker_tag}] {line[:500]}")
    except (ValueError, OSError, AttributeError):
        pass  # pipe closed or process gone


def _read_stdout_live(
    proc: subprocess.Popen,
    worker_tag: str,
    timeout_seconds: int,
) -> tuple[str, int]:
    """Read stdout line-by-line with timeout, return (stdout, exit_code).

    Reads all available stdout lines from a subprocess that also has a
    stderr reader thread running concurrently. Raises
    ``subprocess.TimeoutExpired`` if the process exceeds the timeout.
    """
    stdout_lines: list[str] = []
    start = time.time()
    try:
        for raw_line in iter(proc.stdout.readline, ""):
            elapsed = time.time() - start
            if timeout_seconds > 0 and elapsed > timeout_seconds:
                raise subprocess.TimeoutExpired(
                    cmd=proc.args,
                    timeout=timeout_seconds,
                    output="\n".join(stdout_lines),
                )
            if not raw_line:
                break
            line = raw_line.rstrip("\n\r")
            if line:
                stdout_lines.append(line)
                _log(f"[TERM (worker {worker_tag})] {line[:500]}")
    except (ValueError, OSError, AttributeError):
        pass  # pipe closed or process gone
    proc.wait()
    return "\n".join(stdout_lines), proc.returncode


def _run_hermes_with_pty(
    cmd: list[str],
    worker_tag: str,
    timeout_seconds: int,
    workdir: str,
    heartbeat_timeout: int = 0,
) -> tuple[str, int]:
    """Spawn hermes with a PTY for true line-buffered output.

    Regular pipes cause programs to block-buffer (4KB+). A pseudo-terminal
    forces line-buffered output so we see every tool call and model response
    in real time.

    When ``heartbeat_timeout > 0``, the PTY loop also enforces an idle timeout:
    if no output is received for ``heartbeat_timeout`` seconds the process is
    killed.  This catches silent startup hangs that would otherwise survive
    until the full ``timeout_seconds`` expires.

    Returns (accumulated_stdout, exit_code).
    Raises ``subprocess.TimeoutExpired`` if the process exceeds the timeout.
    """
    lines: list[str] = []
    start = time.time()
    last_output_time = start

    master_fd, slave_fd = pty.openpty()

    proc = subprocess.Popen(
        cmd,
        stdout=slave_fd,
        stderr=slave_fd,  # merge stderr into stdout via PTY
        cwd=workdir or os.getcwd(),
        text=True,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        start_new_session=True,
    )
    os.close(slave_fd)
    os.set_blocking(master_fd, False)

    buffer = ""
    while True:
        elapsed = time.time() - start
        if timeout_seconds > 0 and elapsed > timeout_seconds:
            os.close(master_fd)
            proc.kill()
            proc.wait()
            raise subprocess.TimeoutExpired(cmd, timeout_seconds)

        # Idle timeout: if hermes produces zero output for heartbeat_timeout
        # seconds, it's likely hung during startup — kill it early.
        if heartbeat_timeout > 0:
            idle = time.time() - last_output_time
            if idle > heartbeat_timeout:
                _log(
                    f"[PTY{worker_tag}] No output for {idle:.0f}s "
                    f"(heartbeat={heartbeat_timeout}s) — killing hung session"
                )
                os.close(master_fd)
                proc.kill()
                proc.wait()
                raise subprocess.TimeoutExpired(
                    cmd,
                    heartbeat_timeout,
                    output="\n".join(lines),
                )

        try:
            r, _, _ = select.select([master_fd], [], [], 1.0)
        except (ValueError, OSError):
            break

        if master_fd in r:
            try:
                chunk = os.read(master_fd, 4096).decode("utf-8", errors="replace")
                if not chunk:
                    break
                last_output_time = time.time()
                buffer += chunk
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.rstrip("\r")
                    # Strip ANSI and normalize TUI artifacts
                    clean = _ANSI_RE.sub("", line)
                    # Collapse TUI spinners/indicators
                    clean = clean.replace("┊", "|").replace("✓", "✓").replace("✗", "✗")
                    clean = clean.strip()
                    # Skip pure ANSI/TUI noise lines
                    if (
                        clean
                        and not clean.startswith("@@")
                        and clean not in ("", "│", "╰", "╭")
                    ):
                        lines.append(line)
                        _log(f"[STDOUT{worker_tag}] {clean[:500]}")
                    # Also log raw line (ANSI intact) for terminal rendering in web UI
                    if line.strip():
                        _log(f"[TERM{worker_tag}] {line[:1000]}")
            except (OSError, UnicodeDecodeError):
                break

        if proc.poll() is not None and not buffer:
            break

    if buffer.strip():
        clean = _ANSI_RE.sub("", buffer).strip()
        if clean and not clean.startswith("@@"):
            lines.append(buffer)
            _log(f"[STDOUT{worker_tag}] {clean[:500]}")

    os.close(master_fd)
    exit_code = proc.wait()
    return "\n".join(lines), exit_code


def find_hermes() -> str:
    candidates = [
        shutil.which("hermes"),
        os.path.expanduser("~/.local/bin/hermes"),
        os.path.expanduser("~/.hermes/hermes"),
    ]
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return "hermes"


def detect_task_type(goal: str) -> tuple[str, str, set[str]]:
    """Analyze the goal and detect the primary task type.

    Returns (task_type, description, extra_tools) where extra_tools are
    toolset names to ADD on top of the base set.
    """
    goal_lower = goal.lower()
    scores: dict[str, int] = {}
    for task_type, config in TASK_PATTERNS.items():
        score = sum(1 for kw in config["keywords"] if kw in goal_lower)
        if score > 0:
            scores[task_type] = score

    if not scores:
        return "general", "General task", set()

    best = max(scores, key=scores.get)
    config = TASK_PATTERNS[best]
    return best, config["description"], set(config["extra_toolsets"])


def _build_delegation_prompt(
    iteration: int,
    goal: str,
    context: str,
    toolsets: list[str],
    workdir: str | None,
    evolve: bool,
    worker_id: int | None = None,
    profile: str = "",
    model: str = "",
    provider: str = "",
    prompt_suffix: str = "",
    task_type: str = "general",
    prior_context: str = "",
    heartbeat_interval: int = 0,
) -> str:
    """Build the prompt for a spawned Hermes session.

    The spawned session runs via `hermes chat -q` (NOT -z), which means it
    stays alive for multiple turns. This allows delegate_task() subagent
    results to arrive and be collected. The session has BOTH real tools
    (terminal, file) AND the delegation toolset.

    It MUST print one JSON line as its last output so the daemon can parse it.
    """
    tools_str = ",".join(toolsets)
    worker_tag = f" (worker #{worker_id})" if worker_id is not None else ""

    instructions = [
        f"You are iteration #{iteration}{worker_tag} of an autonomous loop daemon.",
        "",
        "Your job: use your available tools to accomplish the GOAL below, then",
        " report the result as a single JSON line.",
        "",
        f"GOAL: {goal}",
        f"TASK TYPE: {task_type}",
        "",
    ]
    if context:
        instructions.append(f"CONTEXT: {context}")
        instructions.append("")

    if prior_context:
        instructions.append("=== PRIOR ITERATION CONTEXT ===")
        instructions.append(prior_context)
        instructions.append("")
        instructions.append(
            "The above context was recalled from previous iterations. Use it to"
        )
        instructions.append(
            "avoid repeating work or making the same mistakes. If something was"
        )
        instructions.append("already tried and failed, try a different approach.")
        instructions.append("")

    goal_lower = goal.lower()
    if any(
        kw in goal_lower
        for kw in ["infinite-loop", "launch-loop", "self-modif", "skill", "daemon"]
    ):
        skill_dir = os.path.expanduser(
            "~/.hermes/skills/software-development/infinite-loop"
        )
        if os.path.isdir(skill_dir):
            instructions.append("=== SELF-MODIFICATION CONTEXT ===")
            instructions.append(
                f"The daemon's source is at: {skill_dir}/scripts/launch-loop.py"
            )
            instructions.append(f"The skill documentation is at: {skill_dir}/SKILL.md")
            instructions.append(
                "The Hermes Worker is at: ~/.hermes/plugins/hermes-mcp-worker/main.py"
            )
            instructions.append("")
            instructions.append(
                "To signal the daemon to restart with updated code, include"
            )
            instructions.append(
                '"next_goal": "NEXT_ITERATION need_reload" in your JSON output.'
            )
            instructions.append(
                "The daemon will detect this, persist the ledger, and call os.execv()."
            )
            instructions.append(
                "After restart, the NEXT iteration will run with the updated code."
            )
            instructions.append("")

    instructions.extend(
        [
            f"AVAILABLE TOOLS: {tools_str}",
            "",
            "You have full autonomy and these capabilities:",
            "  - terminal: shell commands, build, test, git, packages",
            "  - file: read_file, write_file, patch, search_files",
            "  - web: web_search, web_extract for internet research",
            "  - browser: visual web browsing and interaction",
            "  - skills: skill_view, skills_list for established workflows",
            "  - delegation: delegate_task() — run parallel subagents",
            "  - memory: hindsight_retain/recall/reflect for cross-iteration persistence",
            "  - session_search: find what previous iterations did",
            "  - code_execution: sandboxed Python (import hermes_tools for search/read/terminal)",
            "  - todo: in-session task tracking and planning",
            "  - vision: image analysis and understanding",
            "  - MCP tools: Chroma (vector DB), Cognee (knowledge graph), screenpipe (screen/audio)",
            "",
        ]
    )

    if task_type == "research":
        instructions.extend(
            [
                "=== RESEARCH STRATEGY ===",
                "",
                "1. Start with web_search() to find relevant information",
                "2. Use web_extract() to read key pages in detail",
                "3. If needed, use the browser tool for dynamic page content",
                "4. Use delegate_task() for parallel research threads:",
                "5. Synthesize findings into a clear summary",
                "6. Use hindsight_retain() to save key findings for future iterations",
                "7. Tag findings so future iterations can find them",
                "8. Use skills if workflows exist for this research area",
                "",
                "=== DEEP DELEGATION STRATEGY ===",
                "This session has a HIGH turn budget. Use it:",
                "",
                "1. Break your GOAL into independent research sub-topics",
                "2. Dispatch via delegate_task() — they run in parallel",
                "3. While subagents research, do direct research with your own tools",
                "4. YOUR subagents can ALSO call delegate_task() for multi-level trees",
                "5. Combine all results into the final output",
                "",
            ]
        )
    elif task_type in ("code-fix", "code-build"):
        instructions.extend(
            [
                "=== CODE STRATEGY ===",
                "",
                "1. First, read and understand the relevant files (read_file, search_files)",
                "2. For code-fix: identify the root cause BEFORE making changes",
                "3. For code-build: plan the structure before writing code",
                "4. Write code with write_file() or patch() for targeted edits",
                "5. Use code_execution for quick Python scripts (import hermes_tools)",
                "6. Verify with: linting, type checks, tests",
                "7. Use vision_analyze() for UI/screenshot bugs",
                "8. Use delegate_task() for parallel work:",
                "9. Save findings with hindsight_retain()",
                "10. Use todo() to track subtasks and progress",
                "11. Check skills for established coding workflows",
                "",
                "=== DEEP DELEGATION STRATEGY ===",
                "This session has a HIGH turn budget. Use it aggressively:",
                "",
                "1. Break your GOAL into independent sub-tasks",
                "2. Dispatch via delegate_task() — they run in parallel",
                "3. While subagents work, do direct work with your own tools",
                "4. YOUR subagents can ALSO call delegate_task() for multi-level trees",
                "5. Each subagent can delegate further — build deep trees",
                "6. Combine all results into the final output",
                "",
            ]
        )
    elif task_type == "system-admin":
        instructions.extend(
            [
                "=== SYSTEM ADMIN STRATEGY ===",
                "",
                "1. Check current state first (terminal commands for status, health)",
                "2. Plan changes carefully — consider rollback",
                "3. Use code_execution for automation scripts",
                "4. Verify changes took effect after each step",
                "5. Use delegate_task for parallel configuration:",
                "6. Save system state info with hindsight_retain()",
                "7. Check skills for established system workflows",
                "",
            ]
        )
    elif task_type == "data-processing":
        instructions.extend(
            [
                "=== DATA PROCESSING STRATEGY ===",
                "",
                "1. Examine the data structure first (head, schema, stats)",
                "2. Use code_execution for data transformation (pandas, csv, json)",
                "3. For large datasets, use terminal with command-line tools (jq, awk, sed)",
                "4. Use delegate_task() for parallel data processing:",
                "5. Verify output integrity",
                "6. Save results with write_file()",
                "",
            ]
        )
    elif task_type == "content":
        instructions.extend(
            [
                "=== CONTENT CREATION STRATEGY ===",
                "",
                "1. Research/gather source material first",
                "2. Plan the structure/outline before writing",
                "3. Write with write_file() using proper formatting",
                "4. Use vision_analyze() to understand existing images/diagrams",
                "5. Use delegate_task() for parallel content creation:",
                "6. Review and polish the final output",
                "7. Save with hindsight_retain() if the content is reference material",
                "",
            ]
        )
    else:
        instructions.extend(
            [
                "=== GENERAL STRATEGY ===",
                "",
                "1. Understand the goal and plan your approach",
                "2. Use the most appropriate tools for each sub-task",
                "3. Use delegate_task() for parallel work where possible",
                "4. Verify your work is correct",
                "5. Print JSON summary when done",
                "",
                "=== DEEP DELEGATION STRATEGY ===",
                "This session has a HIGH turn budget. Use it aggressively:",
                "",
                "1. Break your GOAL into independent sub-tasks",
                "2. Dispatch via delegate_task() — they run in parallel",
                "3. While subagents work, do direct work with your own tools",
                "4. YOUR subagents can ALSO call delegate_task() for multi-level trees",
                "5. Combine all results into the final output",
                "",
            ]
        )

    instructions.extend(
        [
            "=== MEMORY & KNOWLEDGE PERSISTENCE ===",
            "You have cross-iteration memory. Use it:",
            "",
            "  hindsight_retain(content, context='infinite-loop', tags=[...])",
            "    - Save important findings for FUTURE iterations",
            "    - Tag with 'project:<name>' so you can find them later",
            "",
            "  hindsight_recall(query='deployment config')",
            "    - Retrieve facts saved by PREVIOUS iterations",
            "    - Use this at the start to understand what's already been done",
            "",
            "  memory(action='add', target='memory', content='...')",
            "    - Save durable facts that persist across all Hermes sessions",
            "    - Use for: project conventions, tool preferences, environment quirks",
            "",
            "  session_search(query='previous work on auth', limit=3)",
            "    - Look at PREVIOUS iterations' full output (beyond summaries)",
            "    - Use this to understand what was already tried and what decisions were made",
            "",
            "  Chroma MCP (chroma_query_documents) — vector search across past data",
            "  Cognee MCP (recall) — knowledge graph search",
            "  todo() — track your subtasks and progress in-session",
            "  code_execution — run sandboxed Python (import hermes_tools for tool access)",
            "",
            "=== TOOL USAGE GUIDELINES ===",
            "",
            "When calling delegate_task():",
            "  - Pass a detailed 'context' field so the subagent works independently",
            "  - Pass toolsets=['terminal','file'] for file-level sub-tasks",
            "  - Pass toolsets=['terminal','file','web'] for research sub-tasks",
            "  - Use batch mode ('tasks' array) for 2-3 parallel subagents",
            "  - Each subagent can delegate further — build deep trees",
            "  - DO use delegate_task() for: code review, testing, research, analysis",
            "  - DO NOT use delegate_task() for: simple file reads, quick commands",
            "",
            "CRITICAL RULES:",
            "1. Actually DO the work — use your tools, don't just describe what to do",
            "2. If you delegate, WAIT for the subagent results to arrive as new messages",
            "3. delegate_task is async — keep working while waiting for subagents",
            "4. Combine subagent results with your direct work into the final output",
            "5. Verify your work is correct (run tests, check output, review changes)",
            "6. Print ONE JSON object on the LAST line of your output",
            "7. Use web_search / web_extract when you need external information",
            "8. Use skills / skill_view when you need established workflows",
            "9. Use hindsight_recall at the START to check what previous iterations learned",
            "10. Use hindsight_retain at the END to save what THIS iteration discovered",
            "11. Use todo() to plan and track your work in-session",
            "12. Prefer direct tool use over delegation for quick operations",
            "13. SELF-MODIFICATION: If your goal is to enhance the daemon or the",
            "    infinite-loop skill itself, use delegate_task() to dispatch a subagent",
            "    that makes the file changes via write_file/patch, then WAIT for its",
            "    result. When done, include 'need_reload' in your JSON's next_goal:",
            '    {"summary": "...", "next_goal": "NEXT_ITERATION need_reload"}',
            "    The daemon will detect this and restart with the updated code.",
            "",
        ]
    )

    if evolve:
        instructions.extend(
            [
                "After completing, think about what the NEXT task should be.",
                "Include a 'next_goal' field in your JSON suggesting what to focus on next.",
                "This should be a natural progression from what you just accomplished.",
            ]
        )

    instructions.extend(
        [
            "",
            "JSON FORMAT (last line of stdout):",
            '  {"summary": "what was done with actual details", "duration_seconds": <int>,',
            (
                '   "error": null|"<error>", "next_goal": "<suggested next task>",'
                if evolve
                else '   "error": null|"<error>",'
            ),
            '   "context": "detailed context for the NEXT iteration to build on this work"}',
            "",
            "  CRITICAL — The 'context' field is how the NEXT iteration knows what you did.",
            "  Include enough detail that iteration N+1 can PICK UP where you left off.",
            "  Mention specific files changed, what was done, what's pending.",
            (
                "  With --evolve, 'next_goal' becomes the goal for the next iteration."
                if evolve
                else ""
            ),
            "  With SELF-MODIFICATION goals, 'context' should describe what files were changed",
            "  and what still needs to be done, so the next iteration doesn't start from zero.",
            "",
            "  SELF-MODIFICATION SIGNAL: If you modified launch-loop.py, the skill, or",
            '  daemon config, set next_goal to "NEXT_ITERATION need_reload" to trigger',
            "  a daemon restart with the updated code.",
            "",
            "ADDITIONAL CONTEXT:",
            f"  Working directory: {workdir or os.getcwd()}",
            f"  Iteration: {iteration}",
            f"  Worker: {worker_id or 'primary'}",
            f"  Task type: {task_type}",
            "  Language: respond in the same language as the context above.",
            "",
            "Do NOT chat or ask questions. Use your tools. Do the work. Print JSON.",
        ]
    )

    if heartbeat_interval > 0:
        instructions.append("")
        instructions.append("=== SESSION HEARTBEAT ===")
        instructions.append(
            f"You MUST emit a heartbeat every {heartbeat_interval} seconds "
            "so the daemon knows you are alive and working."
        )
        instructions.append(
            "Run this shell command every {heartbeat_interval}s (use terminal):"
        )
        instructions.append('  python3 -c "')
        instructions.append("import json, os, time")
        instructions.append("hb = '/tmp/infinite-loop-heartbeat-SESSION_ID'")
        instructions.append("os.makedirs(os.path.dirname(hb), exist_ok=True)")
        instructions.append("with open(hb + '.tmp', 'w') as f:")
        instructions.append("    json.dump({")
        instructions.append("        'session_id': 'SESSION_ID',")
        instructions.append("        'timestamp': time.time(),")
        instructions.append("        'pid': os.getpid()")
        instructions.append("    }, f)")
        instructions.append("os.rename(hb + '.tmp', hb)")
        instructions.append('"')
        instructions.append(
            "Replace SESSION_ID with your actual session or 'unknown-PID'."
        )
        instructions.append(
            "DO NOT skip this — if heartbeats stop, the daemon "
            "will kill and retry this session."
        )
        instructions.append("")

    if prompt_suffix:
        instructions.append("")
        instructions.append("EXTRA INSTRUCTIONS:")
        instructions.append(prompt_suffix)
        instructions.append("")

    return "\n".join(instructions)


def spawn_delegation_session(
    iteration: int,
    goal: str,
    context: str,
    toolsets: list[str],
    workdir: str | None,
    timeout_seconds: int,
    max_output_chars: int = 2000,
    evolve: bool = False,
    worker_id: int | None = None,
    profile: str = "",
    model: str = "",
    provider: str = "",
    prompt_suffix: str = "",
    max_turns: int = 500,
    task_type: str = "general",
    prior_context: str = "",
    worker_url: str = "",
    output_schema: dict | None = None,
    use_library: bool = False,
    pass_session_id: bool = False,
    checkpoints: bool = False,
    resume_session_id: str = "",
    skills: str = "",
    ignore_rules: bool = False,
    yolo: bool = False,
    ignore_user_config: bool = False,
    spawn_source: str = "",
    safe_mode: bool = False,
    accept_hooks: bool = False,
    worktree: bool = False,
    continue_session: bool = False,
    heartbeat_timeout: int = 0,
    iteration_count: int = 0,
) -> dict:
    hermes_bin = find_hermes()
    prompt = _build_delegation_prompt(
        iteration=iteration,
        goal=goal,
        context=context,
        toolsets=toolsets,
        workdir=workdir,
        evolve=evolve,
        worker_id=worker_id,
        profile=profile,
        model=model,
        provider=provider,
        prompt_suffix=prompt_suffix,
        task_type=task_type,
        prior_context=prior_context,
        heartbeat_interval=heartbeat_timeout,
    )
    tools_str = ",".join(toolsets)
    cmd = [
        hermes_bin,
        "chat",
        "-q",
        prompt,
        "-t",
        tools_str,
        "-Q",
        "--max-turns",
        str(max_turns),
    ]
    if profile:
        cmd.extend(["--profile", profile])
    if model:
        cmd.extend(["--model", model])
    if provider:
        cmd.extend(["--provider", provider])

    spawned_session_id = ""
    if pass_session_id:
        cmd.append("--pass-session-id")
    if checkpoints:
        cmd.append("--checkpoints")

    if resume_session_id:
        cmd.extend(["--resume", resume_session_id])
    if skills:
        cmd.extend(["-s", skills])
    if ignore_rules:
        cmd.append("--ignore-rules")

    if yolo:
        cmd.append("--yolo")
    if ignore_user_config:
        cmd.append("--ignore-user-config")
    if spawn_source:
        cmd.extend(["--source", spawn_source])

    if safe_mode:
        cmd.append("--safe-mode")
    if accept_hooks:
        cmd.append("--accept-hooks")
    if worktree:
        cmd.append("--worktree")
    if continue_session:
        cmd.append("--continue")

    worker_tag = f" (worker #{worker_id})" if worker_id is not None else ""
    _log(f"[SPAWN{worker_tag}] hermes chat -q -t {tools_str} (iter #{iteration})")
    _log(f"[SPAWN{worker_tag}] goal: {goal[:120]}...")
    if resume_session_id:
        _log(f"[SPAWN{worker_tag}] Resuming session: {resume_session_id[:12]}...")
    prompt_chars = len(prompt)
    prompt_tokens_est = prompt_chars // 4
    _log(
        f"[SPAWN{worker_tag}] Prompt: ~{prompt_chars} chars (~{prompt_tokens_est} tokens)"
    )

    start = time.time()

    # --- Library mode (--use-library): run AIAgent.run_conversation() in-process ---
    if use_library:
        try:
            _log(
                f"[LIBRARY{worker_tag}] Using AIAgent.run_conversation() in-process (iter #{iteration})"
            )
            if safe_mode or accept_hooks or worktree or continue_session:
                _log(
                    "[LIBRARY] Note: --safe-mode, --accept-hooks, --worktree, --continue are subprocess-only flags (no AIAgent equivalent)"
                )
            from run_agent import AIAgent

            agent = AIAgent(
                model=model or None,
                max_iterations=max_turns,
                enabled_toolsets=list(toolsets),
                quiet_mode=True,
                ephemeral_system_prompt=prompt,
                skip_memory=True,
                checkpoints_enabled=checkpoints,
                pass_session_id=pass_session_id,
                session_id=resume_session_id if resume_session_id else None,
            )
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(agent.run_conversation, user_message=prompt)
                    conv_result = future.result(timeout=timeout_seconds)
            except concurrent.futures.TimeoutError:
                elapsed = time.time() - start
                _log(f"[LIBRARY{worker_tag}] Timed out after {timeout_seconds}s")
                return {
                    "summary": f"TIMEOUT after {timeout_seconds}s (library mode)",
                    "duration_seconds": round(elapsed, 1),
                    "error": f"timed out after {timeout_seconds}s",
                    "error_type": "timeout",
                    "output": "",
                    "exit_code": -1,
                    "spawned_session_id": "",
                }

            elapsed = time.time() - start
            spawned_session_id = conv_result.get("session_id", "") or getattr(
                agent, "session_id", ""
            )
            final_response = conv_result.get("final_response", "")
            parsed_json = extract_json_from_output(final_response)

            if parsed_json:
                result_obj = {
                    "summary": parsed_json.get(
                        "summary", final_response[:max_output_chars]
                    ),
                    "duration_seconds": parsed_json.get(
                        "duration_seconds", round(elapsed, 1)
                    ),
                    "error": parsed_json.get("error"),
                    "next_goal": parsed_json.get("next_goal"),
                    "context": parsed_json.get("context", final_response[:500]),
                    "output": (
                        final_response[:max_output_chars]
                        if max_output_chars > 0
                        else final_response
                    ),
                    "stderr": "",
                    "exit_code": 0,
                    "total_output_bytes": len(final_response),
                    "truncated": max_output_chars > 0
                    and len(final_response) > max_output_chars,
                    "spawned_session_id": spawned_session_id,
                }
                schema_valid = True
                schema_error = ""
                if output_schema:
                    schema_valid, schema_error = validate_json_output(
                        parsed_json, output_schema
                    )
                    if not schema_valid:
                        _log(
                            f"[SCHEMA] Library output validation failed: {schema_error}"
                        )
                    result_obj["schema_valid"] = schema_valid
                    result_obj["schema_error"] = (
                        schema_error if not schema_valid else None
                    )
                output_len = len(final_response)
                result_obj["output_chars"] = output_len
                dur = result_obj["duration_seconds"]
                result_obj["chars_per_second"] = (
                    round(output_len / dur, 1) if dur > 0 else 0
                )
                result_obj["error_type"] = classify_error(result_obj.get("error"))
                _log(
                    f"[LIBRARY{worker_tag}] Complete in {elapsed:.1f}s (session_id={spawned_session_id[:8]}...)"
                )
                return result_obj

            _log(
                f"[LIBRARY{worker_tag}] No JSON extracted from response ({len(final_response)} chars)"
            )
            return {
                "summary": (
                    final_response[:max_output_chars]
                    if final_response
                    else "(no output)"
                ),
                "duration_seconds": round(elapsed, 1),
                "error": None,
                "output": (
                    final_response[:max_output_chars]
                    if max_output_chars > 0
                    else final_response
                ),
                "exit_code": 0,
                "total_output_bytes": len(final_response),
                "truncated": max_output_chars > 0
                and len(final_response) > max_output_chars,
                "spawned_session_id": spawned_session_id,
            }
        except ImportError:
            _log(
                f"[LIBRARY{worker_tag}] AIAgent not importable, falling back to subprocess mode"
            )
        except Exception as e:
            elapsed = time.time() - start
            _log(f"[LIBRARY{worker_tag}] FAILED: {e}, falling back to subprocess mode")

    # --- Worker URL mode: call the Hermes worker over HTTP ---
    if worker_url:
        url = worker_url.rstrip("/") + "/chat"
        payload = json.dumps(
            {
                "prompt": prompt,
                "toolsets": tools_str,
                "timeout": timeout_seconds,
                "workdir": workdir or "",
            }
        )
        try:
            req = urllib.request.Request(
                url,
                data=payload.encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout_seconds + 10) as resp:
                raw = resp.read().decode()
            elapsed = time.time() - start
            result_data = json.loads(raw)
            # Ensure result_data is a dict (worker might return a list/string on error)
            if not isinstance(result_data, dict):
                result_data = {"response": str(result_data), "status": "ok"}

            # Extract response safely — it might be a nested dict
            response_val = result_data.get("response", raw)
            if not isinstance(response_val, str):
                response_val = (
                    json.dumps(response_val)
                    if isinstance(response_val, (dict, list))
                    else str(response_val)
                )

            stdout = (
                response_val[:max_output_chars]
                if max_output_chars > 0
                else response_val
            )
            stderr_val = result_data.get("stderr", "")
            stderr = str(stderr_val)[:1000] if stderr_val else ""
            error = result_data.get("error")
            exit_code = 0 if error is None else 1
            _log(
                f"[WORKER{worker_tag}] Response in {elapsed:.1f}s (status={result_data.get('status', '?')})"
            )
            cap = (
                max_output_chars
                if max_output_chars > 0
                else (
                    len(stdout)
                    if isinstance(stdout, str) and "\n" in stdout
                    else len(raw)
                )
            )
            return {
                "summary": str(stdout)[:cap],
                "duration_seconds": round(elapsed, 1),
                "error": str(error) if error else None,
                "output": (
                    stdout[:max_output_chars]
                    if max_output_chars > 0 and isinstance(stdout, str)
                    else str(stdout)
                ),
                "stderr": stderr,
                "exit_code": exit_code,
                "total_output_bytes": len(raw),
                "truncated": max_output_chars > 0 and len(raw) > max_output_chars,
            }
        except Exception as e:
            elapsed = time.time() - start
            _log(f"[WORKER{worker_tag}] FAILED: {e}")
            return {
                "summary": f"WORKER FAILED: {e}",
                "duration_seconds": round(elapsed, 1),
                "error": str(e),
                "output": "",
                "exit_code": 1,
            }

    # --- Direct subprocess mode (default) ---
    hb_heartbeat_file: str | None = None
    subprocess_exit_code: int = -1
    proc: subprocess.Popen | None = None
    try:
        if heartbeat_timeout > 0:
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=workdir or os.getcwd(),
                text=True,
                env=env,
            )
            session_start = time.time()
            pid = proc.pid
            hb_heartbeat_file = _heartbeat_path(str(pid))

            monitor_thread = threading.Thread(
                target=_run_heartbeat_monitor,
                args=(
                    hb_heartbeat_file,
                    heartbeat_timeout,
                    session_start,
                    proc,
                    timeout_seconds,
                ),
                daemon=True,
            )
            monitor_thread.start()

            # Real-time stderr reader (token/progress feedback)
            stderr_reader = threading.Thread(
                target=_read_stderr_real_time,
                args=(proc, worker_tag),
                daemon=True,
            )
            stderr_reader.start()

            try:
                stdout, subprocess_exit_code = _read_stdout_live(
                    proc, worker_tag, timeout_seconds
                )
                stderr_reader.join(timeout=2)
                elapsed = time.time() - start
                stderr = ""  # already streamed by stderr_reader
            except subprocess.TimeoutExpired:
                elapsed = time.time() - start
                _kill_session(proc, str(pid))
                _cleanup_heartbeat_file(hb_heartbeat_file)
                return {
                    "summary": f"TIMEOUT after {timeout_seconds}s",
                    "duration_seconds": round(elapsed, 1),
                    "error": f"timed out after {timeout_seconds}s",
                    "error_type": "timeout",
                    "output": "",
                    "exit_code": -1,
                    "spawned_session_id": "",
                }
        else:
            try:
                stdout, subprocess_exit_code = _run_hermes_with_pty(
                    cmd,
                    worker_tag,
                    timeout_seconds,
                    workdir or os.getcwd(),
                    heartbeat_timeout=heartbeat_timeout,
                )
            except subprocess.TimeoutExpired:
                elapsed = time.time() - start
                return {
                    "summary": f"TIMEOUT after {timeout_seconds}s",
                    "duration_seconds": round(elapsed, 1),
                    "error": f"timed out after {timeout_seconds}s",
                    "error_type": "timeout",
                    "output": "",
                    "exit_code": -1,
                    "spawned_session_id": "",
                }
            elapsed = time.time() - start
            stderr = ""

        extracted_session_id = ""
        for line in (stdout or "").split("\n"):
            stripped = line.strip()
            if stripped.startswith("session_id:"):
                extracted_session_id = stripped.split(":", 1)[1].strip()
                break
        spawned_session_id = extracted_session_id

        parsed_json = extract_json_from_output(stdout)

        output_cap = max_output_chars if max_output_chars > 0 else len(stdout)
        stderr_cap = max_output_chars if max_output_chars > 0 else len(stderr)
        actual_output_len = len(stdout)
        was_truncated = max_output_chars > 0 and actual_output_len > max_output_chars

        if parsed_json:
            schema_valid = True
            schema_error = ""
            if output_schema:
                schema_valid, schema_error = validate_json_output(
                    parsed_json, output_schema
                )
                if not schema_valid:
                    _log(f"[SCHEMA] Output schema validation failed: {schema_error}")

            # Coerce summary to string — hermes might return nested dicts
            raw_summary = parsed_json.get("summary", stdout[:output_cap])
            safe_summary = (
                json.dumps(raw_summary)
                if isinstance(raw_summary, (dict, list))
                else (
                    str(raw_summary) if raw_summary is not None else stdout[:output_cap]
                )
            )
            # Determine error from JSON content only — not from subprocess exit code.
            # Hermes often exits non-zero even on successful runs (e.g. stderr
            # warnings), so exit code alone should NOT produce a false error.
            json_error = parsed_json.get("error")
            if json_error is not None and str(json_error).strip():
                effective_error = str(json_error)
            elif not schema_valid:
                effective_error = schema_error
            else:
                effective_error = None
            result_obj = {
                "summary": safe_summary,
                "duration_seconds": parsed_json.get(
                    "duration_seconds", round(elapsed, 1)
                ),
                "error": effective_error,
                "next_goal": (
                    str(parsed_json.get("next_goal"))
                    if parsed_json.get("next_goal")
                    else None
                ),
                "context": str(parsed_json.get("context", "")),
                "output": stdout[:output_cap],
                "stderr": stderr[:stderr_cap],
                "exit_code": subprocess_exit_code,
                "schema_valid": schema_valid,
                "schema_error": schema_error if not schema_valid else None,
            }
            output_len = len(stdout)
            result_obj["output_chars"] = output_len
            result_obj["total_output_bytes"] = actual_output_len
            result_obj["truncated"] = was_truncated
            dur = result_obj["duration_seconds"]
            result_obj["chars_per_second"] = (
                round(output_len / dur, 1) if dur > 0 else 0
            )
            result_obj["error_type"] = classify_error(result_obj.get("error"))
            result_obj["spawned_session_id"] = spawned_session_id
            return result_obj

        summary = str(stdout[:output_cap]) if stdout else "(no output)"
        if subprocess_exit_code != 0:
            output_len = len(stdout or "")
            # If the session produced actual output (not just an error), treat
            # it as success — hermes often exits non-zero with stderr warnings
            # even after a perfectly successful run that produced useful stdout.
            if output_len > 30:
                return {
                    "summary": summary,
                    "duration_seconds": round(elapsed, 1),
                    "error": None,
                    "output": stdout[:output_cap],
                    "stderr": str(stderr[:stderr_cap]),
                    "exit_code": subprocess_exit_code,
                    "total_output_bytes": actual_output_len,
                    "truncated": was_truncated,
                    "spawned_session_id": spawned_session_id,
                }
            # Exit code non-zero with no meaningful output -> probably a real failure
            # But check if stderr has a useful summary (hermes may print results to stderr)
            stderr_output = stderr or ""
            if len(stderr_output.strip()) > 50:
                # Stderr has meaningful content — treat as success (hermes logging)
                return {
                    "summary": (
                        str(summary)[:output_cap]
                        if summary
                        else str(stderr_output)[:output_cap]
                    ),
                    "duration_seconds": round(elapsed, 1),
                    "error": None,
                    "output": stdout[:output_cap],
                    "stderr": str(stderr[:stderr_cap]),
                    "exit_code": subprocess_exit_code,
                    "total_output_bytes": actual_output_len,
                    "truncated": was_truncated,
                    "spawned_session_id": spawned_session_id,
                }
            summary = f"FAILED (exit {subprocess_exit_code}): {str(stderr[:300])}"
            return {
                "summary": summary,
                "duration_seconds": round(elapsed, 1),
                "error": f"hermes exit {subprocess_exit_code}",
                "error_type": "unknown",
                "output": str(stdout + "\n" + stderr)[:output_cap],
                "stderr": str(stderr[:stderr_cap]),
                "exit_code": subprocess_exit_code,
                "total_output_bytes": actual_output_len,
                "truncated": was_truncated,
                "spawned_session_id": spawned_session_id,
            }

        return {
            "summary": summary,
            "duration_seconds": round(elapsed, 1),
            "error": None,
            "output": stdout[:output_cap],
            "stderr": stderr[:stderr_cap],
            "exit_code": subprocess_exit_code,
            "total_output_bytes": actual_output_len,
            "truncated": was_truncated,
            "spawned_session_id": spawned_session_id,
        }

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        _log(f"[TIMEOUT] Hermes session timed out after {timeout_seconds}s")
        return {
            "summary": f"TIMEOUT after {timeout_seconds}s",
            "duration_seconds": round(elapsed, 1),
            "error": f"timed out after {timeout_seconds}s",
            "error_type": "timeout",
            "output": "",
            "exit_code": -1,
            "spawned_session_id": spawned_session_id if spawned_session_id else "",
        }
    except FileNotFoundError:
        return {
            "summary": "FAILED: hermes binary not found",
            "duration_seconds": 0,
            "error": "hermes binary not found on PATH",
            "error_type": "network",
            "output": "",
            "exit_code": -1,
            "spawned_session_id": "",
        }
    except Exception as e:
        elapsed = time.time() - start
        return {
            "summary": f"FAILED: {e}",
            "duration_seconds": round(elapsed, 1),
            "error": str(e),
            "error_type": classify_error(str(e)),
            "output": "",
            "exit_code": -1,
            "spawned_session_id": spawned_session_id if spawned_session_id else "",
        }
