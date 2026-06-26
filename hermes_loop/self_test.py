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
                lambda r: (r == 60, f"expected 60, got {r}"),
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
                lambda r: (r is True, f"basic GoalSpec assertion failed"),
            )
        )

        def _with_profile():
            g = GoalSpec("fix auth", profile="work")
            return g.goal == "fix auth" and g.profile == "work"

        cases.append(
            (
                "with-profile",
                lambda: _with_profile(),
                lambda r: (r is True, f"with-profile GoalSpec assertion failed"),
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
                lambda r: (r is True, f"full-spec GoalSpec assertion failed"),
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
        # Network error should suggest connectivity checks
        cases.append(
            (
                "network-suggestion",
                lambda: _suggest_actionable_fix("network", "stuck", "deploy api"),
                lambda r: (
                    r is not None and "network" in r.lower(),
                    f"expected network suggestion, got {r!r}",
                ),
            )
        )
        # Stuck classification with workers>1 should suggest --workers 1
        cases.append(
            (
                "stuck-workers-suggestion",
                lambda: _suggest_actionable_fix(None, "stuck", "fix bug", workers=3),
                lambda r: (
                    r is not None and "--workers" in r,
                    f"expected workers suggestion for stuck, got {r!r}",
                ),
            )
        )
        # Stuck classification with library mode should NOT mention workers
        cases.append(
            (
                "stuck-library-no-workers-tip",
                lambda: _suggest_actionable_fix(
                    None, "stuck", "fix bug", workers=3, use_library=True
                ),
                lambda r: (
                    r is not None and "--workers" not in r,
                    f"expected NOT to mention -workers in library mode, got {r!r}",
                ),
            )
        )
        # Regression should suggest reviewing git diff
        cases.append(
            (
                "regression-suggestion",
                lambda: _suggest_actionable_fix(None, "regression", "refactor db"),
                lambda r: (
                    r is not None and "git diff" in r.lower(),
                    f"expected git diff suggestion for regression, got {r!r}",
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
