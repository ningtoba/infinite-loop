"""Tests for web_app.config_manager — config schema and CLI args."""

from unittest.mock import patch

from web_app.config_manager import (
    CONFIG_DEFAULTS,
    _read_stored,
    build_cli_args,
    get_config,
    get_raw_config,
    save_config,
    validate_config,
)

# ── Helpers ──────────────────────────────────────────────────────────────


def _mock_stored(overrides: dict[str, str] | None = None) -> dict[str, str]:
    """Return a dict shaped like omp_loop.config_file.load_config() output."""
    defaults = {k: v["default"] for k, v in CONFIG_DEFAULTS.items()}
    if overrides:
        defaults.update(overrides)
    return defaults


# ── TestReadStored ───────────────────────────────────────────────────────


class TestReadStored:
    """_read_stored() — loads + normalises stored config."""

    def test_returns_defaults(self):
        """When no stored values exist, _read_stored returns defaults."""
        with patch("web_app.config_manager.load_config", return_value={}):
            result = _read_stored()
        for key, meta in CONFIG_DEFAULTS.items():
            assert result[key] == meta["default"], f"mismatch for {key}"

    def test_reads_file_values(self):
        """_read_stored merges file values on top of defaults."""
        stored = {"INFINITE_LOOP_GOAL": "build stuff", "INFINITE_LOOP_GIT": "true"}
        with patch("web_app.config_manager.load_config", return_value=stored):
            result = _read_stored()
        assert result["INFINITE_LOOP_GOAL"] == "build stuff"
        assert result["INFINITE_LOOP_GIT"] == "true"
        # Other keys still have defaults
        assert result["INFINITE_LOOP_MAX_ITERATIONS"] == CONFIG_DEFAULTS["INFINITE_LOOP_MAX_ITERATIONS"]["default"]
        assert result["INFINITE_LOOP_COOLDOWN"] == CONFIG_DEFAULTS["INFINITE_LOOP_COOLDOWN"]["default"]


# ── TestSaveConfig ────────────────────────────────────────────────────────


class TestSaveConfig:
    """save_config() — delegates to omp_loop.config_file.save_config."""

    def test_saves(self):
        """save_config calls the underlying _save_config with the dict."""
        payload = {"INFINITE_LOOP_GOAL": "my goal"}
        with patch("web_app.config_manager._save_config") as mock_save:
            save_config(payload)
        mock_save.assert_called_once_with(payload)


# ── TestValidateConfig ────────────────────────────────────────────────────


class TestValidateConfig:
    """validate_config() — checks required fields."""

    def test_valid(self):
        """All required fields present → valid."""
        config = _mock_stored({"INFINITE_LOOP_GOAL": "build stuff"})
        result = validate_config(config)
        assert result["valid"]
        assert result["errors"] == []

    def test_with_error(self):
        """Missing required field → invalid with descriptive error."""
        config = _mock_stored({"INFINITE_LOOP_GOAL": ""})
        result = validate_config(config)
        assert not result["valid"]
        errors: list[str] = result["errors"]  # type: ignore[assignment]
        assert len(errors) == 1
        assert "INFINITE_LOOP_GOAL" in errors[0]


# ── TestGetConfig ─────────────────────────────────────────────────────────


class TestGetConfig:
    """get_config() — schema + current values."""

    def test_returns_schema(self):
        """get_config returns CONFIG_DEFAULTS enriched with 'value' keys."""
        with patch("web_app.config_manager.load_config", return_value={}):
            result = get_config()
        for key in CONFIG_DEFAULTS:
            assert key in result
            entry = result[key]
            assert "value" in entry
            assert entry["value"] == CONFIG_DEFAULTS[key]["default"]
            assert "type" in entry
            assert "group" in entry
            assert "label" in entry


# ── TestGetRawConfig ──────────────────────────────────────────────────────


class TestGetRawConfig:
    """get_raw_config() — raw key-value dict."""

    def test_returns_raw(self):
        """get_raw_config returns the dict from _read_stored with current values."""
        stored = {"INFINITE_LOOP_GOAL": "my goal", "INFINITE_LOOP_GIT": "true"}
        with patch("web_app.config_manager.load_config", return_value=stored):
            result = get_raw_config()
        assert result["INFINITE_LOOP_GOAL"] == "my goal"
        assert result["INFINITE_LOOP_GIT"] == "true"
        # non-overridden keys get defaults
        assert result["INFINITE_LOOP_QUIET"] == CONFIG_DEFAULTS["INFINITE_LOOP_QUIET"]["default"]


# ── TestBuildCliArgs ──────────────────────────────────────────────────────


class TestBuildCliArgs:
    """build_cli_args() — builds CLI arguments from config."""

    def test_with_goal(self):
        """Goal is mapped to --goal flag."""
        config = _mock_stored({"INFINITE_LOOP_GOAL": "run tests"})
        args = build_cli_args(config)
        assert "--goal" in args
        idx = args.index("--goal")
        assert args[idx + 1] == "run tests"

    def test_with_git(self):
        """Git enabled → --git flag present."""
        config = _mock_stored({"INFINITE_LOOP_GIT": "true"})
        args = build_cli_args(config)
        assert "--git" in args

    def test_git_off_by_default(self):
        """Git disabled by default → --git not present."""
        config = _mock_stored()
        args = build_cli_args(config)
        assert "--git" not in args

    def test_with_context(self):
        """Context is mapped to --append-system-prompt."""
        config = _mock_stored({"INFINITE_LOOP_CONTEXT": "be concise"})
        args = build_cli_args(config)
        assert "--append-system-prompt" in args
        idx = args.index("--append-system-prompt")
        assert args[idx + 1] == "be concise"

    def test_empty_config(self):
        """Empty/non-overridden config produces no CLI flags."""
        config = _mock_stored()
        args = build_cli_args(config)
        # No values differ from defaults → empty args
        assert args == []

    def test_non_string_value_types(self):
        """Numeric and bool values get correct flag treatment."""
        config = _mock_stored(
            {
                "INFINITE_LOOP_MAX_ITERATIONS": "99",
                "INFINITE_LOOP_COOLDOWN": "5",
                "INFINITE_LOOP_QUIET": "true",
            }
        )
        args = build_cli_args(config)
        assert "--max-iterations" in args
        assert "--cooldown" in args
        assert "--quiet" in args

    def test_all_bool_flags(self):
        """All boolean flags are emitted when set to 'true'."""
        bool_keys = [
            "INFINITE_LOOP_GIT",
            "INFINITE_LOOP_GIT_COMMIT",
            "INFINITE_LOOP_STORE_GIT_DIFF",
            "INFINITE_LOOP_NOTIFY_DESKTOP",
            "INFINITE_LOOP_STOP_AT_GOALS_END",
            "INFINITE_LOOP_TRACK_GOALS",
            "INFINITE_LOOP_RESET_GOALS",
            "INFINITE_LOOP_QUIET",
            "INFINITE_LOOP_PREFLIGHT",
            "INFINITE_LOOP_PREFLIGHT_FAIL_FAST",
            "INFINITE_LOOP_DRY_RUN",
        ]
        config = _mock_stored(dict.fromkeys(bool_keys, "true"))
        args = build_cli_args(config)
        expected_flags = {
            "--git",
            "--git-commit",
            "--store-git-diff",
            "--notify-desktop",
            "--stop-at-goals-end",
            "--track-goals",
            "--reset-goals",
            "--quiet",
            "--preflight",
            "--preflight-fail-fast",
            "--dry-run",
        }
        for flag in expected_flags:
            assert flag in args, f"{flag} should be present"
