"""Integrated self-test suite for daemon functions."""

import re
from datetime import datetime, timezone

from .file_utils import extract_json_from_output
from .error_utils import classify_error, _classify_progress, _suggest_actionable_fix
from .similarity import text_similarity, check_convergence
from .validation import validate_json_output
from .cooldown import calc_adaptive_cooldown
from .goal_utils import GoalSpec


def count_self_test_cases(source_path: str | None = None) -> dict:
    """Count self-test groups and cases by introspecting the test functions.

    Returns {'groups': N, 'cases': N} where groups are test functions and
    cases are calls to cases.append() within each test function.
    This is a static-code-analysis approach that stays correct as tests evolve
    without requiring manual count updates.

    The counting is done inside _run_self_test()'s body to avoid counting
    this function's own source code.
    """
    if source_path is None:
        import os

        source_path = os.path.join(os.path.dirname(__file__), "self_test.py")

    groups = 0
    cases = 0
    try:
        with open(source_path) as f:
            content = f.read()

        # Count test groups (functions named _test_*) — only inside _run_self_test
        # Find the _run_self_test function body
        match = re.search(
            r"def _run_self_test\(\) -> dict:.*?(?=\n\ndef |\Z)",
            content,
            re.DOTALL,
        )
        if match:
            body = match.group()
            test_funcs = re.findall(r"def (_test_\w+)\(\):", body)
            groups = len(test_funcs)
            # Count cases.append calls within test functions only
            cases = body.count("cases.append(")
    except (FileNotFoundError, IOError):
        pass

    return {"groups": groups, "cases": cases}


def _run_self_test() -> dict:
    """Run integrated self-test suite to verify daemon functions in isolation.

    Returns a dict with keys: passed, failed, total, results.
    """
    results: list[dict] = []
    passed_total = 0
    failed_total = 0

    def _record(test_name: str, passed: bool, detail: str = "") -> None:
        nonlocal passed_total, failed_total
        if passed:
            passed_total += 1
        else:
            failed_total += 1
        results.append({"name": test_name, "passed": passed, "detail": detail})

    def _run_subtests(group: str, cases: list[tuple[str, callable, callable]]) -> None:
        nonlocal passed_total, failed_total
        passed_cases = 0
        failed_cases: list[str] = []
        for case_name, func, validator in cases:
            try:
                result = func()
                ok, detail = validator(result)
                if ok:
                    passed_cases += 1
                else:
                    failed_cases.append(f"{case_name}: {detail}")
            except Exception as e:
                failed_cases.append(f"{case_name}: EXCEPTION: {e}")
        total_cases = len(cases)
        if failed_cases:
            detail = "; ".join(failed_cases)
            ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
            print(
                f"[{ts}] [SELF-TEST] \u2717 {group} ({passed_cases}/{total_cases} cases passed): {detail}",
                flush=True,
            )
            _record(group, False, detail)
        else:
            ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
            print(
                f"[{ts}] [SELF-TEST] \u2713 {group} ({passed_cases}/{total_cases} cases passed)",
                flush=True,
            )
            _record(group, True, "")

    # ------------------------------------------------------------------
    # Test: extract_json_output
    # ------------------------------------------------------------------
    def _test_extract_json():
        cases = []
        cases.append(
            (
                "single-line",
                lambda: extract_json_from_output('{"summary": "hello", "error": null}'),
                lambda r: (r is not None and r.get("summary") == "hello", f"got {r}"),
            )
        )
        cases.append(
            (
                "multi-line",
                lambda: extract_json_from_output(
                    '{\n"summary": "hello",\n"error": null\n}'
                ),
                lambda r: (r is not None and r.get("summary") == "hello", f"got {r}"),
            )
        )
        cases.append(
            (
                "code-fence",
                lambda: extract_json_from_output(
                    '```json\n{"summary": "hello", "error": null}\n```'
                ),
                lambda r: (r is not None and r.get("summary") == "hello", f"got {r}"),
            )
        )
        cases.append(
            (
                "session-noise",
                lambda: extract_json_from_output(
                    'session_id: abc-123\n{"summary": "hello", "error": null}'
                ),
                lambda r: (r is not None and r.get("summary") == "hello", f"got {r}"),
            )
        )
        cases.append(
            (
                "empty",
                lambda: extract_json_from_output(""),
                lambda r: (r is None, f"expected None, got {r}"),
            )
        )
        cases.append(
            (
                "none-input",
                lambda: extract_json_from_output(None),
                lambda r: (r is None, f"expected None, got {r}"),
            )
        )
        return cases

    _run_subtests("test_extract_json_output", _test_extract_json())

    # ------------------------------------------------------------------
    # Test: classify_error
    # ------------------------------------------------------------------
    def _test_classify_error():
        cases = []
        cases.append(
            (
                "none",
                lambda: classify_error(None),
                lambda r: (r is None, f"expected None, got {r!r}"),
            )
        )
        cases.append(
            (
                "timeout",
                lambda: classify_error("timeout"),
                lambda r: (r == "timeout", f"expected 'timeout', got {r!r}"),
            )
        )
        cases.append(
            (
                "connection-refused",
                lambda: classify_error("connection refused"),
                lambda r: (r == "network", f"expected 'network', got {r!r}"),
            )
        )
        cases.append(
            (
                "schema-validation",
                lambda: classify_error("schema validation failed"),
                lambda r: (r == "schema", f"expected 'schema', got {r!r}"),
            )
        )
        cases.append(
            (
                "random-error",
                lambda: classify_error("random error"),
                lambda r: (r == "unknown", f"expected 'unknown', got {r!r}"),
            )
        )
        return cases

    _run_subtests("test_classify_error", _test_classify_error())

    # ------------------------------------------------------------------
    # Test: text_similarity
    # ------------------------------------------------------------------
    def _test_text_similarity():
        cases = []
        cases.append(
            (
                "identical",
                lambda: text_similarity("hello world", "hello world"),
                lambda r: (r == 1.0, f"expected 1.0, got {r}"),
            )
        )
        cases.append(
            (
                "completely-different",
                lambda: text_similarity("abc", "xyz"),
                lambda r: (r == 0.0, f"expected 0.0, got {r}"),
            )
        )
        cases.append(
            (
                "partial-overlap",
                lambda: text_similarity("hello world foo", "hello bar"),
                lambda r: (0.0 < r < 1.0, f"expected 0<r<1, got {r}"),
            )
        )
        cases.append(
            (
                "both-empty",
                lambda: text_similarity("", ""),
                lambda r: (r == 1.0, f"expected 1.0, got {r}"),
            )
        )
        cases.append(
            (
                "one-empty",
                lambda: text_similarity("hello", ""),
                lambda r: (r == 0.0, f"expected 0.0, got {r}"),
            )
        )
        return cases

    _run_subtests("test_text_similarity", _test_text_similarity())

    # ------------------------------------------------------------------
    # Test: check_convergence
    # ------------------------------------------------------------------
    def _test_check_convergence():
        cases = []
        cases.append(
            (
                "fewer-than-window",
                lambda: check_convergence(["a"], threshold=0.9, window=3),
                lambda r: (not r[0] and r[1] == 0.0, f"got {r}"),
            )
        )
        cases.append(
            (
                "all-identical",
                lambda: check_convergence(["hello world"] * 5, threshold=0.9, window=5),
                lambda r: (r[0] is True and r[1] == 1.0, f"got {r}"),
            )
        )
        cases.append(
            (
                "all-different",
                lambda: check_convergence(
                    ["abc", "def", "ghi", "jkl", "mno"], threshold=0.9, window=5
                ),
                lambda r: (not r[0] and r[1] < 1.0, f"got {r}"),
            )
        )
        return cases

    _run_subtests("test_check_convergence", _test_check_convergence())

    # ------------------------------------------------------------------
    # Test: validate_json_output
    # ------------------------------------------------------------------
    def _test_validate_json():
        schema = {
            "type": "object",
            "required": ["summary", "status"],
            "properties": {
                "summary": {"type": "string"},
                "status": {"type": "string", "enum": ["ok", "error"]},
            },
        }
        valid_out = {"summary": "done", "status": "ok"}
        cases = []
        cases.append(
            (
                "valid",
                lambda: validate_json_output(valid_out, schema),
                lambda r: (r[0] is True, f"expected True, got {r}"),
            )
        )
        cases.append(
            (
                "missing-field",
                lambda: validate_json_output({"summary": "done"}, schema),
                lambda r: (
                    r[0] is False and "missing required field" in r[1],
                    f"got {r}",
                ),
            )
        )
        cases.append(
            (
                "wrong-type",
                lambda: validate_json_output({"summary": 42, "status": "ok"}, schema),
                lambda r: (
                    r[0] is False and "expected string, got int" in r[1].lower(),
                    f"got {r}",
                ),
            )
        )
        cases.append(
            (
                "no-schema",
                lambda: validate_json_output({"summary": "x"}, None),
                lambda r: (r[0] is True, f"got {r}"),
            )
        )
        return cases

    _run_subtests("test_validate_json_output", _test_validate_json())

    # ------------------------------------------------------------------
    # Test: calc_adaptive_cooldown
    # ------------------------------------------------------------------
    def _test_calc_cooldown():
        cases = []
        cases.append(
            (
                "zero-duration",
                lambda: calc_adaptive_cooldown(0, min_cooldown=2, max_cooldown=60),
                lambda r: (r == 2, f"expected 2, got {r}"),
            )
        )
        cases.append(
            (
                "long-duration",
                lambda: calc_adaptive_cooldown(300, min_cooldown=2, max_cooldown=60),
                lambda r: (r == 2, f"expected 2, got {r}"),
            )
        )
        cases.append(
            (
                "short-duration",
                lambda: calc_adaptive_cooldown(5, min_cooldown=2, max_cooldown=60),
                lambda r: (
                    r > 50 and r <= 60,
                    f"expected ~59 (smooth interpolation), got {r}",
                ),
            )
        )
        cases.append(
            (
                "medium-duration",
                lambda: calc_adaptive_cooldown(60, min_cooldown=5, max_cooldown=120),
                lambda r: (5 < r < 120, f"expected 5<r<120, got {r}"),
            )
        )
        cases.append(
            (
                "interpolated",
                lambda: calc_adaptive_cooldown(30, min_cooldown=2, max_cooldown=60),
                lambda r: (2 < r < 60, f"expected 2<r<60, got {r}"),
            )
        )
        return cases

    _run_subtests("test_calc_adaptive_cooldown", _test_calc_cooldown())

    # ------------------------------------------------------------------
    # Test: GoalSpec
    # ------------------------------------------------------------------
    def _test_goal_spec():
        cases = []

        def _basic():
            g = GoalSpec("fix auth")
            return (
                g.goal == "fix auth"
                and g.profile == ""
                and g.model == ""
                and g.provider == ""
            )

        cases.append(
            (
                "basic",
                lambda: _basic(),
                lambda r: (r is True, "basic GoalSpec assertion failed"),
            )
        )

        def _with_profile():
            g = GoalSpec("fix auth", profile="work")
            return g.goal == "fix auth" and g.profile == "work"

        cases.append(
            (
                "with-profile",
                lambda: _with_profile(),
                lambda r: (r is True, "with-profile GoalSpec assertion failed"),
            )
        )

        def _full():
            g = GoalSpec("fix auth", profile="work", model="gpt4", provider="openai")
            return (
                g.goal == "fix auth"
                and g.profile == "work"
                and g.model == "gpt4"
                and g.provider == "openai"
            )

        cases.append(
            (
                "full-spec",
                lambda: _full(),
                lambda r: (r is True, "full-spec GoalSpec assertion failed"),
            )
        )
        return cases

    _run_subtests("test_goal_spec", _test_goal_spec())

    # ------------------------------------------------------------------
    # Test: _classify_progress
    # ------------------------------------------------------------------
    def _test_classify_progress():
        cases = []
        cases.append(
            (
                "completed",
                lambda: _classify_progress("task completed", None, None, None),
                lambda r: (r == "completed", f"expected 'completed', got {r!r}"),
            )
        )
        cases.append(
            (
                "regression",
                lambda: _classify_progress(
                    "something broke", None, None, "error occurred"
                ),
                lambda r: (r == "regression", f"expected 'regression', got {r!r}"),
            )
        )
        cases.append(
            (
                "stuck",
                lambda: _classify_progress("fail", None, None, None),
                lambda r: (r == "stuck", f"expected 'stuck', got {r!r}"),
            )
        )
        git_before = {"diff_stat": "0 files"}
        git_after = {"diff_stat": "1 file changed"}
        cases.append(
            (
                "progress",
                lambda: _classify_progress(
                    "fixed the bug", git_before, git_after, None
                ),
                lambda r: (r == "progress", f"expected 'progress', got {r!r}"),
            )
        )
        return cases

    _run_subtests("test_classify_progress", _test_classify_progress())

    # ------------------------------------------------------------------
    # Test: _suggest_actionable_fix
    # ------------------------------------------------------------------
    def _test_suggest_actionable_fix():
        cases = []
        # Completed/progress should return None (no suggestion)
        cases.append(
            (
                "completed-no-suggestion",
                lambda: _suggest_actionable_fix(None, "completed", "fix tests"),
                lambda r: (
                    r is None,
                    f"expected None for completed, got {r!r}",
                ),
            )
        )
        cases.append(
            (
                "progress-no-suggestion",
                lambda: _suggest_actionable_fix(None, "progress", "implement feature"),
                lambda r: (
                    r is None,
                    f"expected None for progress, got {r!r}",
                ),
            )
        )
        # Stuck without extra flags should suggest use-library and evolve
        cases.append(
            (
                "stuck-suggestion",
                lambda: _suggest_actionable_fix(None, "stuck", "fix bug"),
                lambda r: (
                    r is not None and "--use-library" in r and "--evolve" in r,
                    f"expected --use-library and --evolve suggestion, got {r!r}",
                ),
            )
        )
        # Stuck with workers > 1 should suggest reducing workers
        cases.append(
            (
                "stuck-multiworker",
                lambda: _suggest_actionable_fix(
                    None, "stuck", "fix auth", workers=3, use_library=False
                ),
                lambda r: (
                    r is not None and "--workers 1" in r and "--use-library" in r,
                    f"expected worker+library fix, got {r!r}",
                ),
            )
        )
        # Timeout error should suggest session-timeout increase
        cases.append(
            (
                "timeout-suggestion",
                lambda: _suggest_actionable_fix("timeout", "stuck", "refactor auth"),
                lambda r: (
                    r is not None and "--session-timeout" in r,
                    f"expected timeout suggestion, got {r!r}",
                ),
            )
        )
        # High-consecutive-errors (3+) with unknown error type
        cases.append(
            (
                "high-consecutive-errors",
                lambda: _suggest_actionable_fix(
                    "unknown", "stuck", "fix whatever", consecutive_errors=3
                ),
                lambda r: (
                    r is not None and "--preflight" in r,
                    f"expected preflight suggestion, got {r!r}",
                ),
            )
        )
        # Regression with ALL flags already enabled should suggest nothing
        cases.append(
            (
                "regression-suggestion-all-enabled",
                lambda: _suggest_actionable_fix(
                    None,
                    "regression",
                    "refactor db",
                    git=True,
                    git_commit=True,
                    force_reset=True,
                ),
                lambda r: (
                    r is None,
                    f"expected no suggestion when git+git-commit+force-reset all enabled, got {r!r}",
                ),
            )
        )
        # Regression with only git enabled should skip --git but still suggest others
        cases.append(
            (
                "regression-suggestion-git-only",
                lambda: _suggest_actionable_fix(
                    None,
                    "regression",
                    "refactor db",
                    git=True,
                ),
                lambda r: (
                    r is not None
                    and "Add --git to track"
                    not in r  # should NOT suggest adding the --git flag
                    and "--git-commit" in r
                    and "--force-reset" in r,
                    f"expected --git-commit+force-reset (no --git flag) for git-only, got {r!r}",
                ),
            )
        )
        # Consecutive errors >= 3 should suggest preflight
        cases.append(
            (
                "consecutive-errors-suggestion",
                lambda: _suggest_actionable_fix(
                    "unknown", "stuck", "deploy app", consecutive_errors=5
                ),
                lambda r: (
                    r is not None and "--preflight" in r,
                    f"expected preflight suggestion for 5 consecutive errors, got {r!r}",
                ),
            )
        )
        # Schema error should suggest output-schema review
        cases.append(
            (
                "schema-suggestion",
                lambda: _suggest_actionable_fix("schema", "stuck", "parse data"),
                lambda r: (
                    r is not None and "--output-schema" in r,
                    f"expected schema suggestion, got {r!r}",
                ),
            )
        )
        return cases

    _run_subtests("test_suggest_actionable_fix", _test_suggest_actionable_fix())

    # ------------------------------------------------------------------
    # Test: env_utils — validate_env_vars
    # ------------------------------------------------------------------
    def _test_validate_env_vars():
        from .env_utils import validate_env_vars, KNOWN_ENV_VARS, _find_closest_match

        cases = []

        # Known variable should return type "ok"
        cases.append(
            (
                "known-var",
                lambda: validate_env_vars({"INFINITE_LOOP_GOAL": "fix tests"}),
                lambda r: (
                    any(
                        x["type"] == "ok" and x["key"] == "INFINITE_LOOP_GOAL"
                        for x in r
                    ),
                    f"expected ok for known var, got {r}",
                ),
            )
        )

        # Typo should be detected
        cases.append(
            (
                "typo-detection",
                lambda: validate_env_vars({"INFINITE_LOOP_COOL_DOWN": "10"}),
                lambda r: (
                    any(
                        x["type"] == "typo"
                        and "INFINITE_LOOP_COOLDOWN" in x.get("message", "")
                        for x in r
                    ),
                    f"expected typo detection for COOL_DOWN, got {r}",
                ),
            )
        )

        # Unknown var (no close match) should return type "unknown"
        cases.append(
            (
                "unknown-var",
                lambda: validate_env_vars({"INFINITE_LOOP_ZZZZZZ": "test"}),
                lambda r: (
                    any(
                        x["type"] == "unknown" and x["key"] == "INFINITE_LOOP_ZZZZZZ"
                        for x in r
                    ),
                    f"expected unknown for ZZZZZZ, got {r}",
                ),
            )
        )

        # Non-INFINITE_LOOP_ var should return type "warning"
        cases.append(
            (
                "non-prefix-var",
                lambda: validate_env_vars({"MY_CUSTOM_VAR": "value"}),
                lambda r: (
                    any(
                        x["type"] == "warning" and x["key"] == "MY_CUSTOM_VAR"
                        for x in r
                    ),
                    f"expected warning for non-prefix var, got {r}",
                ),
            )
        )

        # _find_closest_match should return closest known var name
        cases.append(
            (
                "closest-match",
                lambda: _find_closest_match("INFINITE_LOOP_COOL_DOWN", KNOWN_ENV_VARS),
                lambda r: (
                    r == "INFINITE_LOOP_COOLDOWN",
                    f"expected COOLDOWN, got {r!r}",
                ),
            )
        )

        # _find_closest_match returns None for very different names
        cases.append(
            (
                "no-close-match",
                lambda: _find_closest_match("COMPLETELY_UNRELATED", KNOWN_ENV_VARS),
                lambda r: (
                    r is None,
                    f"expected None, got {r!r}",
                ),
            )
        )

        # Missing common required vars
        cases.append(
            (
                "missing-goal",
                lambda: validate_env_vars({}),
                lambda r: (
                    any(
                        x["type"] == "missing" and x["key"] == "INFINITE_LOOP_GOAL"
                        for x in r
                    ),
                    f"expected missing GOAL warning, got {r}",
                ),
            )
        )

        return cases

    _run_subtests("test_validate_env_vars", _test_validate_env_vars())

    # ------------------------------------------------------------------
    # Test: bounded-queue broadcast paths — queue.Full drop, stale-client
    # sweep, isinstance backward-compat, and concurrent access.
    # ------------------------------------------------------------------
    def _test_bounded_queue():
        from queue import Queue, Full as QueueFull
        import time
        import threading

        cases = []

        # ── queue.Full drop ──────────────────────────────────────────
        # Create a tiny bounded queue, fill it, then verify put_nowait
        # raises QueueFull (and our broadcast helper would drop the
        # client rather than grow unbounded).
        def _test_queue_full_drop():
            q: Queue = Queue(maxsize=1)
            # Fill the queue (the only slot)
            q.put_nowait("payload1")
            try:
                q.put_nowait("payload2")
                return False  # should have raised
            except QueueFull:
                pass
            # Verify that the underlying queue still respects maxsize
            # and the client hasn't grown unbounded
            return q.qsize() == 1

        cases.append(
            (
                "queue-full-drops-slow-client",
                _test_queue_full_drop,
                lambda r: (
                    r is True,
                    "expected maxsize=1 queue to stay at 1, got qsize check",
                ),
            )
        )

        # ── Stale-client sweep ───────────────────────────────────────
        # Simulate _broadcast_to_sse_clients' stale-sweep logic:
        # clients with last_active older than _CLIENT_STALE_TIMEOUT
        # should be skipped.
        _CLIENT_STALE_TIMEOUT = 60.0

        def _test_stale_sweep():
            now = time.monotonic()
            q_stale: Queue = Queue(maxsize=128)
            q_fresh: Queue = Queue(maxsize=128)
            # Simulate the tracking dict and sweep logic
            last_active = {
                id(q_stale): now - _CLIENT_STALE_TIMEOUT - 10.0,  # stale (>60s ago)
                id(q_fresh): now - 5.0,  # fresh (<60s ago)
            }
            alive = []
            for q in [q_stale, q_fresh]:
                qid = id(q)
                la = last_active.get(qid, now)
                if now - la > _CLIENT_STALE_TIMEOUT:
                    continue  # stale — skip
                try:
                    q.put_nowait("payload")
                    alive.append(q)
                except QueueFull:
                    pass
            # Fresh client should have been put to, stale should not
            fresh_has_item = q_fresh.qsize() == 1
            stale_has_item = q_stale.qsize() == 0
            return fresh_has_item and stale_has_item and len(alive) == 1

        cases.append(
            (
                "stale-client-sweep-skips-dead-clients",
                _test_stale_sweep,
                lambda r: (
                    r is True,
                    "expected only fresh client in alive list, stale skipped",
                ),
            )
        )

        # ── isinstance backward-compat ───────────────────────────────
        # The webhook.py _handle_sse line ~190 does:
        #   raw = json.loads(data) if isinstance(data, str) else data
        # Verify this handles both str and dict inputs correctly.

        def _test_isinstance_compat():
            import json

            # str path — json.loads
            str_data = '{"summary": "hello"}'
            raw_str = json.loads(str_data) if isinstance(str_data, str) else str_data
            # dict path — pass through
            dict_data = {"summary": "hello"}
            raw_dict = (
                json.loads(dict_data) if isinstance(dict_data, str) else dict_data
            )
            # Both should produce identical dicts
            return (
                raw_str == raw_dict
                and isinstance(raw_str, dict)
                and isinstance(raw_dict, dict)
            )

        cases.append(
            (
                "isinstance-backward-compat-str-and-dict",
                _test_isinstance_compat,
                lambda r: (r is True, "isinstance compat failed"),
            )
        )

        # ── Concurrent access ────────────────────────────────────────
        # Simulate concurrent broadcast + client add/remove to verify
        # no deadlocks or data races using threading primitives.

        def _test_concurrent_access():

            n_clients = 16
            n_broadcasts = 8
            lock = threading.Lock()
            clients = [Queue(maxsize=128) for _ in range(n_clients)]
            dropped = [0]

            def _broadcast_worker():
                for _ in range(n_broadcasts):
                    with lock:
                        alive = []
                        for q in clients:
                            try:
                                q.put_nowait("data")
                                alive.append(q)
                            except QueueFull:
                                dropped[0] += 1
                        clients[:] = alive

            def _add_worker():
                for _ in range(n_broadcasts // 2):
                    new_q = Queue(maxsize=128)
                    with lock:
                        clients.append(new_q)

            def _remove_worker():
                for _ in range(n_broadcasts // 2):
                    with lock:
                        if clients:
                            clients.pop()

            threads = []
            for fn in (
                [_broadcast_worker] * 3 + [_add_worker] * 2 + [_remove_worker] * 2
            ):
                t = threading.Thread(target=fn, daemon=True)
                threads.append(t)
                t.start()
            for t in threads:
                t.join(timeout=5.0)
            # All threads should complete without deadlock
            # At least 0 dropped (may be 0) — no crash is the pass condition
            return all(not t.is_alive() for t in threads)

        cases.append(
            (
                "concurrent-broadcast-no-deadlock",
                _test_concurrent_access,
                lambda r: (
                    r is True,
                    "thread deadlock or timeout during concurrent broadcast",
                ),
            )
        )

        return cases

    _run_subtests("test_bounded_queue_broadcast", _test_bounded_queue())

    # ------------------------------------------------------------------
    # Test: signal_handlers — _build_exec_argv
    # ------------------------------------------------------------------
    def _test_build_exec_argv():
        from .signal_handlers import _build_exec_argv

        cases = []
        import sys as _sys

        _orig_argv = list(_sys.argv)

        # Wrapper: set argv, call func, return result
        def _with_argv(argv, fn):
            _sys.argv.clear()
            _sys.argv.extend(argv)
            return fn()

        # Normal invocation: python3 launch-loop.py --run
        def _run_normal():
            return _with_argv(["launch-loop.py", "--run"], _build_exec_argv)

        cases.append(
            (
                "normal-invocation",
                _run_normal,
                lambda r: (
                    r == [_sys.executable, "launch-loop.py", "--run"],
                    f"expected [executable, launch-loop.py, --run], got {r!r}",
                ),
            )
        )

        # Module invocation: python3 -m hermes_loop --run
        def _run_module():
            return _with_argv(["-m", "hermes_loop", "--run"], _build_exec_argv)

        cases.append(
            (
                "module-invocation",
                _run_module,
                lambda r: (
                    r == [_sys.executable, "-m", "hermes_loop", "--run"],
                    f"expected [executable, -m, hermes_loop, --run], got {r!r}",
                ),
            )
        )

        # Module with extra args
        def _run_module_args():
            return _with_argv(
                ["-m", "hermes_loop", "--run", "--workers", "3"], _build_exec_argv
            )

        cases.append(
            (
                "module-with-args",
                _run_module_args,
                lambda r: (
                    r
                    == [
                        _sys.executable,
                        "-m",
                        "hermes_loop",
                        "--run",
                        "--workers",
                        "3",
                    ],
                    f"expected multi-arg argv, got {r!r}",
                ),
            )
        )

        # Restore original argv after all cases
        _sys.argv.clear()
        _sys.argv.extend(_orig_argv)
        return cases

    _run_subtests("test_build_exec_argv", _test_build_exec_argv())

    total = passed_total + failed_total
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    if failed_total == 0:
        print(
            f"[{ts}] [SELF-TEST] Result: {passed_total}/{total} tests passed, all OK",
            flush=True,
        )
    else:
        print(
            f"[{ts}] [SELF-TEST] Result: {passed_total}/{total} tests passed, {failed_total} FAILURES",
            flush=True,
        )

    return {
        "passed": passed_total,
        "failed": failed_total,
        "total": total,
        "results": results,
    }
