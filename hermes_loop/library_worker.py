"""Library worker — multiprocessing workers for --use-library."""

import logging as _logging
import sys
import time
import concurrent.futures as _cf

from .config import LOG_FORMAT, LOG_DATE_FORMAT
from .file_utils import _log, extract_json_from_output
from .error_utils import classify_error
from .validation import validate_json_output


def _setup_worker_logging(prefix: str = "") -> None:
    """Configure per-worker logging in child process."""

    root = _logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = _logging.StreamHandler(sys.stdout)
    handler.setFormatter(_logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))
    root.addHandler(handler)
    root.setLevel(_logging.DEBUG)


def _build_library_result(
    conv_result: dict,
    final_response: str,
    spawned_session_id: str,
    elapsed: float,
    max_output_chars: int,
    output_schema: dict | None,
) -> dict:
    """Build the result dict from an AIAgent conversation result."""
    parsed_json = extract_json_from_output(final_response)

    if parsed_json:
        result_obj = {
            "summary": parsed_json.get("summary", final_response[:max_output_chars]),
            "duration_seconds": parsed_json.get("duration_seconds", round(elapsed, 1)),
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
        if output_schema:
            schema_valid, schema_error = validate_json_output(
                parsed_json, output_schema
            )
            result_obj["schema_valid"] = schema_valid
            result_obj["schema_error"] = schema_error if not schema_valid else None
        output_len = len(final_response)
        result_obj["output_chars"] = output_len
        dur = result_obj["duration_seconds"]
        result_obj["chars_per_second"] = round(output_len / dur, 1) if dur > 0 else 0
        result_obj["error_type"] = classify_error(result_obj.get("error"))
        return result_obj

    return {
        "summary": (
            final_response[:max_output_chars] if final_response else "(no output)"
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
        "truncated": max_output_chars > 0 and len(final_response) > max_output_chars,
        "spawned_session_id": spawned_session_id,
    }


def _library_worker(config: dict, prompt: str, worker_id: int) -> dict:
    """Run a single AIAgent conversation in a child process."""
    from run_agent import AIAgent

    start = time.time()
    _setup_worker_logging(f"[LIBRARY (worker #{worker_id})]")

    try:
        agent = AIAgent(
            model=config.get("model") or None,
            max_iterations=config.get("max_iterations", 500),
            enabled_toolsets=config.get("enabled_toolsets", []),
            quiet_mode=True,
            ephemeral_system_prompt=prompt,
            skip_memory=True,
            checkpoints_enabled=config.get("checkpoints_enabled", False),
            pass_session_id=config.get("pass_session_id", False),
            session_id=config.get("session_id", None),
        )
        try:
            with _cf.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(agent.run_conversation, user_message=prompt)
                timeout_seconds = config.get("timeout_seconds", 7200)
                conv_result = future.result(timeout=timeout_seconds)
        except _cf.TimeoutError:
            elapsed = time.time() - start
            return {
                "summary": f"WORKER #{worker_id} TIMEOUT after {config.get('timeout_seconds', 7200)}s",
                "duration_seconds": round(elapsed, 1),
                "error": "timeout",
                "error_type": "timeout",
                "output": "",
                "exit_code": -1,
                "spawned_session_id": "",
                "worker_id": worker_id,
            }

        elapsed = time.time() - start
        spawned_session_id = conv_result.get("session_id", "") or getattr(
            agent, "session_id", ""
        )
        final_response = conv_result.get("final_response", "")

        return _build_library_result(
            conv_result,
            final_response,
            spawned_session_id,
            elapsed,
            config.get("max_output_chars", 2000),
            config.get("output_schema"),
        )

    except Exception as e:
        elapsed = time.time() - start
        return {
            "summary": f"WORKER #{worker_id} FAILED: {e}",
            "duration_seconds": round(elapsed, 1),
            "error": str(e),
            "error_type": classify_error(str(e)),
            "output": "",
            "exit_code": -1,
            "spawned_session_id": "",
            "worker_id": worker_id,
        }


def _run_library_workers_parallel(
    tasks: list[tuple[dict, str, int]], workers: int
) -> list[dict]:
    """Run library-mode workers in parallel using multiprocessing."""
    try:
        import multiprocessing as _mp

        ctx = _mp.get_context("spawn")
    except (ImportError, ValueError):
        try:
            import multiprocessing as _mp

            ctx = _mp.get_context("fork")
        except (ImportError, ValueError):
            return _run_library_workers_sequential(tasks)

    try:
        with ctx.Pool(processes=min(workers, len(tasks))) as pool:
            return list(pool.starmap(_library_worker, tasks))
    except (OSError, RuntimeError, Exception) as e:
        _log(f"[LIBRARY] Pool creation failed ({e}), falling back to sequential")
        return _run_library_workers_sequential(tasks)


def _run_library_workers_sequential(tasks: list[tuple[dict, str, int]]) -> list[dict]:
    """Run workers one at a time as a last resort fallback."""
    results = []
    for config, prompt, worker_id in tasks:
        try:
            r = _library_worker(config, prompt, worker_id)
            results.append(r)
        except Exception as e:
            results.append(
                {
                    "summary": f"WORKER #{worker_id} FAILED: {e}",
                    "duration_seconds": 0,
                    "error": str(e),
                    "output": "",
                    "exit_code": -1,
                    "worker_id": worker_id,
                }
            )
    return results
