"""Tests for web_app.config_manager — config schema, JSON persistence, CLI arg building."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch


from web_app.config_manager import (
    CONFIG_DEFAULTS,
    CONFIG_GROUPS,
    build_cli_args,
    get_config_with_defaults,
    get_raw_config,
    read_json_config,
    write_json_config,
)

# ============================================================================
# Section 1: CONFIG_DEFAULTS structure (8 tests)
# ============================================================================


class TestConfigDefaults:
    """Verify the schema of every CONFIG_DEFAULTS entry."""

    REQUIRED_KEYS = {"default", "type", "group", "label", "description"}
    VALID_TYPES = {"string", "bool", "int", "float", "select"}
    VALID_GROUPS = {g["id"] for g in CONFIG_GROUPS}

    def test_all_entries_have_required_keys(self):
        """Every CONFIG_DEFAULTS entry must have default, type, group, label, description."""
        for key, meta in CONFIG_DEFAULTS.items():
            missing = self.REQUIRED_KEYS - set(meta.keys())
            assert not missing, f"{key} missing keys: {missing}"

    def test_all_entries_have_valid_type(self):
        """Every entry's type must be one of string, bool, int, float, select."""
        for key, meta in CONFIG_DEFAULTS.items():
            assert (
                meta["type"] in self.VALID_TYPES
            ), f"{key} has invalid type {meta['type']!r}"

    def test_all_entries_have_valid_group(self):
        """Every entry's group must exist in CONFIG_GROUPS."""
        for key, meta in CONFIG_DEFAULTS.items():
            assert (
                meta["group"] in self.VALID_GROUPS
            ), f"{key} has invalid group {meta['group']!r}"

    def test_required_flag_true_for_core_goal(self):
        """The GOAL entry should have required=True."""
        assert CONFIG_DEFAULTS["INFINITE_LOOP_GOAL"].get("required") is True

    def test_select_entries_have_options_list(self):
        """Entries of type 'select' must have an 'options' key."""
        for key, meta in CONFIG_DEFAULTS.items():
            if meta["type"] == "select":
                assert (
                    "options" in meta
                ), f"{key} is type 'select' but missing 'options'"
                assert isinstance(
                    meta["options"], list
                ), f"{key} options must be a list"

    def test_multiline_flag_is_optional(self):
        """'multiline' key should only appear on entries that need it."""
        for key, meta in CONFIG_DEFAULTS.items():
            if "multiline" in meta:
                assert isinstance(
                    meta["multiline"], bool
                ), f"{key} multiline must be bool"

    def test_all_keys_start_with_infinite_loop_prefix(self):
        """Every config key must start with INFINITE_LOOP_."""
        for key in CONFIG_DEFAULTS:
            assert key.startswith(
                "INFINITE_LOOP_"
            ), f"{key} lacks INFINITE_LOOP_ prefix"

    def test_no_duplicate_keys(self):
        """CONFIG_DEFAULTS dict should have no duplicate keys (enforced by dict)."""
        assert len(CONFIG_DEFAULTS) == len(set(CONFIG_DEFAULTS))


# ============================================================================
# Section 2: CONFIG_GROUPS structure (3 tests)
# ============================================================================


class TestConfigGroups:
    """Verify the structure of every CONFIG_GROUPS entry."""

    def test_all_groups_have_id_name_icon(self):
        for g in CONFIG_GROUPS:
            assert "id" in g, f"Group missing 'id': {g}"
            assert "name" in g, f"Group {g['id']} missing 'name'"
            assert "icon" in g, f"Group {g['id']} missing 'icon'"

    def test_group_ids_unique(self):
        ids = [g["id"] for g in CONFIG_GROUPS]
        assert len(ids) == len(set(ids)), "Duplicate group IDs found"

    def test_every_default_group_referenced_in_config(self):
        """Every group id in CONFIG_GROUPS must have at least one config entry."""
        group_ids = {g["id"] for g in CONFIG_GROUPS}
        used_ids = {meta["group"] for meta in CONFIG_DEFAULTS.values()}
        unused = group_ids - used_ids
        assert not unused, f"Unused groups (zero config entries): {unused}"


# ============================================================================
# Section 3: read_json_config (5 tests)
# ============================================================================


class TestReadJsonConfig:
    """Tests for read_json_config(path)."""

    def test_file_exists_valid_json(self, tmp_path: Path):
        """Returns filtered dict when file contains valid JSON with INFINITE_LOOP_ keys."""
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "INFINITE_LOOP_GOAL": "test goal",
                    "INFINITE_LOOP_RUN": "true",
                    "NON_LOOP_KEY": "should be filtered",
                }
            )
        )
        result = read_json_config(str(config_file))
        assert result == {
            "INFINITE_LOOP_GOAL": "test goal",
            "INFINITE_LOOP_RUN": "true",
        }

    def test_file_not_exists(self, tmp_path: Path):
        """Returns empty dict when file doesn't exist."""
        result = read_json_config(str(tmp_path / "nonexistent.json"))
        assert result == {}

    def test_invalid_json(self, tmp_path: Path):
        """Returns empty dict on JSONDecodeError."""
        config_file = tmp_path / "bad.json"
        config_file.write_text("this is not json")
        result = read_json_config(str(config_file))
        assert result == {}

    def test_file_contains_list(self, tmp_path: Path):
        """Returns empty dict when JSON root is a list, not a dict."""
        config_file = tmp_path / "list.json"
        config_file.write_text("[1, 2, 3]")
        result = read_json_config(str(config_file))
        assert result == {}

    def test_default_path_used_when_none_given(self):
        """Uses CONFIG_PATH when no explicit path is given."""
        with (patch("web_app.config_manager.os.path.exists", return_value=False),):
            result = read_json_config()
            assert result == {}


# ============================================================================
# Section 4: write_json_config (4 tests)
# ============================================================================


class TestWriteJsonConfig:
    """Tests for write_json_config(config, path)."""

    def test_writes_to_path(self, tmp_path: Path):
        """Writes the config dict as formatted JSON to the given path."""
        config_file = tmp_path / "subdir" / "config.json"
        config = {"INFINITE_LOOP_GOAL": "test"}
        write_json_config(config, str(config_file))
        assert config_file.exists()
        data = json.loads(config_file.read_text())
        assert data == config

    def test_creates_parent_directories(self, tmp_path: Path):
        """Creates parent dirs automatically via os.makedirs."""
        config_file = tmp_path / "deep" / "nested" / "dir" / "config.json"
        write_json_config({"k": "v"}, str(config_file))
        assert config_file.exists()

    def test_overwrites_existing_file(self, tmp_path: Path):
        """Overwrites an existing file with new data."""
        config_file = tmp_path / "existing.json"
        config_file.write_text(json.dumps({"old": "data"}))
        write_json_config({"new": "data"}, str(config_file))
        data = json.loads(config_file.read_text())
        assert data == {"new": "data"}

    def test_indent_format(self, tmp_path: Path):
        """Output JSON should be indented with 2 spaces."""
        config_file = tmp_path / "indent.json"
        write_json_config({"a": "b"}, str(config_file))
        content = config_file.read_text()
        assert '  "a"' in content  # 2-space indent


# ============================================================================
# Section 5: get_config_with_defaults (4 tests)
# ============================================================================


class TestGetConfigWithDefaults:
    """Tests for get_config_with_defaults()."""

    def test_returns_all_default_keys(self):
        """Returns every key from CONFIG_DEFAULTS."""
        with (patch("web_app.config_manager.read_json_config", return_value={}),):
            result = get_config_with_defaults()
            assert set(result.keys()) == set(CONFIG_DEFAULTS.keys())

    def test_merges_current_values(self):
        """Current config values override defaults when present."""
        with (
            patch(
                "web_app.config_manager.read_json_config",
                return_value={"INFINITE_LOOP_GOAL": "my goal"},
            ),
        ):
            result = get_config_with_defaults()
            assert result["INFINITE_LOOP_GOAL"]["value"] == "my goal"

    def test_keeps_default_when_no_current(self):
        """Uses default value when no current value exists."""
        with (patch("web_app.config_manager.read_json_config", return_value={}),):
            result = get_config_with_defaults()
            assert result["INFINITE_LOOP_GOAL"]["value"] == ""

    def test_every_entry_has_value_key(self):
        """Every result entry must contain a 'value' field."""
        with (patch("web_app.config_manager.read_json_config", return_value={}),):
            result = get_config_with_defaults()
            for key, entry in result.items():
                assert "value" in entry, f"{key} missing 'value'"


# ============================================================================
# Section 6: get_raw_config (4 tests)
# ============================================================================


class TestGetRawConfig:
    """Tests for get_raw_config()."""

    def test_returns_flat_key_value_dict(self):
        """Returns a flat dict with key -> str value for every default."""
        with (patch("web_app.config_manager.read_json_config", return_value={}),):
            result = get_raw_config()
            assert isinstance(result, dict)
            assert set(result.keys()) == set(CONFIG_DEFAULTS.keys())

    def test_values_are_strings(self):
        """All values in raw config should be strings."""
        with (patch("web_app.config_manager.read_json_config", return_value={}),):
            result = get_raw_config()
            for k, v in result.items():
                assert isinstance(v, str), f"{k} value is {type(v)} not str"

    def test_injects_current_values(self):
        """Current persisted values override defaults."""
        with (
            patch(
                "web_app.config_manager.read_json_config",
                return_value={"INFINITE_LOOP_RUN": "true"},
            ),
        ):
            result = get_raw_config()
            assert result["INFINITE_LOOP_RUN"] == "true"

    def test_returns_default_for_unset_keys(self):
        """Unset keys still get their default value."""
        with (patch("web_app.config_manager.read_json_config", return_value={}),):
            result = get_raw_config()
            assert result["INFINITE_LOOP_RUN"] == "false"


# ============================================================================
# Section 7: build_cli_args (7+ tests)
# ============================================================================


class TestBuildCliArgs:
    """Tests for build_cli_args(config)."""

    def test_string_flag_appended(self):
        """String flags with non-default values appear in args."""
        config = {"INFINITE_LOOP_GOAL": "build a rocket"}
        args = build_cli_args(config)
        assert "--goal" in args
        idx = args.index("--goal")
        assert args[idx + 1] == "build a rocket"

    def test_bool_flag_appended(self):
        """Boolean flags with 'true' value appear as standalone flags."""
        config = {"INFINITE_LOOP_RUN": "true"}
        args = build_cli_args(config)
        assert "--run" in args

    def test_bool_flag_skipped_when_false(self):
        """Boolean flags with 'false' value are NOT included."""
        config = {"INFINITE_LOOP_RUN": "false"}
        args = build_cli_args(config)
        assert "--run" not in args

    def test_default_values_skipped(self):
        """String flags with default values are NOT included."""
        config = {"INFINITE_LOOP_WEBHOOK_PORT": "0"}  # default
        args = build_cli_args(config)
        assert "--webhook-port" not in args

    def test_empty_string_skipped(self):
        """Empty string values are skipped for string flags."""
        config = {"INFINITE_LOOP_GOAL": ""}
        args = build_cli_args(config)
        assert "--goal" not in args

    def test_multiple_flags_all_present(self):
        """Multiple config values produce all corresponding flags."""
        config = {
            "INFINITE_LOOP_GOAL": "test goal",
            "INFINITE_LOOP_RUN": "true",
            "INFINITE_LOOP_GIT": "true",
            "INFINITE_LOOP_MAX_ITERATIONS": "10",
        }
        args = build_cli_args(config)
        assert "--goal" in args
        assert "--run" in args
        assert "--git" in args
        assert "--max-iterations" in args

    def test_unknown_key_is_ignored(self):
        """Keys not in str_flags or bool_flags are silently skipped."""
        config = {"NONEXISTENT_KEY": "value", "INFINITE_LOOP_RUN": "true"}
        args = build_cli_args(config)
        assert "--run" in args
        # Ensure no unknown flag was added
        assert "--nonexistent-key" not in args


# ============================================================================
# Section 8: Edge cases for build_cli_args (4+ tests)
# ============================================================================


class TestBuildCliArgsEdgeCases:
    """Edge-case and integration-style tests for build_cli_args."""

    def test_empty_config_produces_no_args(self):
        """An empty config dict should return an empty list (no flags)."""
        args = build_cli_args({})
        assert args == []

    def test_all_bools_true(self):
        """All bool flags present when every bool config is 'true'."""
        bool_keys = [
            "INFINITE_LOOP_EVOLVE",
            "INFINITE_LOOP_RUN",
            "INFINITE_LOOP_GIT",
            "INFINITE_LOOP_GIT_COMMIT",
            "INFINITE_LOOP_STORE_GIT_DIFF",
            "INFINITE_LOOP_NOTIFY_DESKTOP",
            "INFINITE_LOOP_NOTIFY_ON_COMPLETION",
            "INFINITE_LOOP_CONVERGENCE_STOP",
            "INFINITE_LOOP_QUIET",
            "INFINITE_LOOP_NO_AUTO_TOOLSETS",
            "INFINITE_LOOP_NO_FAILURE_LEARNING",
            "INFINITE_LOOP_STOP_AT_GOALS_END",
            "INFINITE_LOOP_TRACK_GOALS",
            "INFINITE_LOOP_RESET_GOALS",
            "INFINITE_LOOP_USE_LIBRARY",
            "INFINITE_LOOP_PASS_SESSION_ID",
            "INFINITE_LOOP_CHECKPOINTS",
            "INFINITE_LOOP_RESUME",
            "INFINITE_LOOP_IGNORE_RULES",
            "INFINITE_LOOP_IGNORE_USER_CONFIG",
            "INFINITE_LOOP_YOLO",
            "INFINITE_LOOP_SAFE_MODE",
            "INFINITE_LOOP_ACCEPT_HOOKS",
            "INFINITE_LOOP_WORKTREE",
            "INFINITE_LOOP_CONTINUE",
            "INFINITE_LOOP_PREFLIGHT",
            "INFINITE_LOOP_PREFLIGHT_FAIL_FAST",
            "INFINITE_LOOP_DRY_RUN",
            "INFINITE_LOOP_SELF_TEST",
        ]
        config = {k: "true" for k in bool_keys}
        args = build_cli_args(config)
        # All should be present — map to expected flag names
        expected_flags = [
            "--evolve",
            "--run",
            "--git",
            "--git-commit",
            "--store-git-diff",
            "--notify-desktop",
            "--notify-on-completion",
            "--convergence-stop",
            "--quiet",
            "--no-auto-toolsets",
            "--no-failure-learning",
            "--stop-at-goals-end",
            "--track-goals",
            "--reset-goals",
            "--use-library",
            "--pass-session-id",
            "--checkpoints",
            "--resume",
            "--ignore-rules",
            "--ignore-user-config",
            "--yolo",
            "--safe-mode",
            "--accept-hooks",
            "--worktree",
            "--continue",
            "--preflight",
            "--preflight-fail-fast",
            "--dry-run",
            "--self-test",
        ]
        for flag in expected_flags:
            assert flag in args, f"Expected {flag} in args but not found"

    def test_bool_flag_case_insensitive(self):
        """Boolean flags match with mixed case 'True'."""
        config = {"INFINITE_LOOP_RUN": "True"}
        args = build_cli_args(config)
        assert "--run" in args

    def test_non_matching_key_cli_value_present(self):
        """When a value differs from default, it appears in args."""
        config = {"INFINITE_LOOP_WEBHOOK_PORT": "8080"}  # default is "0"
        args = build_cli_args(config)
        assert "--webhook-port" in args
        idx = args.index("--webhook-port")
        assert args[idx + 1] == "8080"

    def test_output_schema_multiline_in_cli(self):
        """Multiline string values should still appear as proper args."""
        config = {"INFINITE_LOOP_OUTPUT_SCHEMA": '{"type": "object"}'}
        args = build_cli_args(config)
        assert "--output-schema" in args
        idx = args.index("--output-schema")
        assert args[idx + 1] == '{"type": "object"}'
