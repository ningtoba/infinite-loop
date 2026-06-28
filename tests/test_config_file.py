"""Tests for pi_loop.config_file — JSON config persistence."""

import json
import os
from unittest.mock import patch

from pi_loop.config_file import (
    DEFAULTS,
    apply_to_environ,
    ensure_config_dir,
    get,
    get_bool,
    load_config,
    save_config,
)


class TestEnsureConfigDir:
    def test_creates_directory(self, tmp_path):
        """ensure_config_dir creates ~/.config/pi-loop."""
        with (
            patch("pi_loop.config_file.CONFIG_DIR", tmp_path),
            patch("pi_loop.config_file.CONFIG_PATH", tmp_path / "config.json"),
        ):
            ensure_config_dir()
        assert tmp_path.exists()

    def test_no_error_if_exists(self, tmp_path):
        """ensure_config_dir is idempotent — no error if dir exists."""
        tmp_path.mkdir(parents=True, exist_ok=True)
        with (
            patch("pi_loop.config_file.CONFIG_DIR", tmp_path),
            patch("pi_loop.config_file.CONFIG_PATH", tmp_path / "config.json"),
        ):
            ensure_config_dir()
        assert tmp_path.exists()


class TestLoadConfig:
    def test_returns_defaults_when_no_file(self, tmp_path):
        """load_config returns DEFAULTS when config file does not exist."""
        config_path = tmp_path / "config.json"
        with patch("pi_loop.config_file.CONFIG_DIR", tmp_path), patch("pi_loop.config_file.CONFIG_PATH", config_path):
            result = load_config()
        for k, v in DEFAULTS.items():
            assert result[k] == v, f"Mismatch for {k}"

    def test_merges_with_defaults(self, tmp_path):
        """load_config merges stored values on top of defaults."""
        config_dir = tmp_path
        config_path = config_dir / "config.json"
        stored = {"INFINITE_LOOP_GOAL": "custom goal", "INFINITE_LOOP_RUN": "true"}
        with open(config_path, "w") as f:
            json.dump(stored, f)
        with patch("pi_loop.config_file.CONFIG_DIR", config_dir), patch("pi_loop.config_file.CONFIG_PATH", config_path):
            result = load_config()
        assert result["INFINITE_LOOP_GOAL"] == "custom goal"
        assert result["INFINITE_LOOP_RUN"] == "true"
        assert result["INFINITE_LOOP_TIMEOUT"] == "600"

    def test_corrupted_file_returns_defaults(self, tmp_path):
        """load_config returns defaults when config file is corrupted."""
        config_path = tmp_path / "config.json"
        config_path.write_text("invalid json{{{")
        with patch("pi_loop.config_file.CONFIG_DIR", tmp_path), patch("pi_loop.config_file.CONFIG_PATH", config_path):
            result = load_config()
        for k, v in DEFAULTS.items():
            assert result[k] == v, f"Mismatch for {k}"

    def test_oserror_returns_defaults(self, tmp_path):
        """load_config returns defaults on OSError."""
        config_path = tmp_path / "config.json"
        config_path.write_text("{}")
        with (
            patch("pi_loop.config_file.CONFIG_DIR", tmp_path),
            patch("pi_loop.config_file.CONFIG_PATH", config_path),
            patch("builtins.open", side_effect=OSError("permission denied")),
        ):
            result = load_config()
        for k, v in DEFAULTS.items():
            assert result[k] == v, f"Mismatch for {k}"


class TestSaveConfig:
    def test_persists_values(self, tmp_path):
        """save_config writes merged values to disk."""
        config_path = tmp_path / "config.json"
        with patch("pi_loop.config_file.CONFIG_DIR", tmp_path), patch("pi_loop.config_file.CONFIG_PATH", config_path):
            save_config(
                {"INFINITE_LOOP_GOAL": "test goal", "INFINITE_LOOP_RUN": "true", "INFINITE_LOOP_NEW_KEY": "custom"}
            )
        assert config_path.exists()
        with open(config_path) as f:
            data = json.load(f)
        assert data["INFINITE_LOOP_GOAL"] == "test goal"
        assert data["INFINITE_LOOP_RUN"] == "true"
        assert data["INFINITE_LOOP_NEW_KEY"] == "custom"
        assert "INFINITE_LOOP_TIMEOUT" in data

    def test_oserror_silent(self, tmp_path):
        """save_config does not raise on OSError."""
        config_path = tmp_path / "config.json"
        with (
            patch("pi_loop.config_file.CONFIG_DIR", tmp_path),
            patch("pi_loop.config_file.CONFIG_PATH", config_path),
            patch("builtins.open", side_effect=OSError("read-only")),
        ):
            result = save_config({"INFINITE_LOOP_GOAL": "test"})
        assert result is not None


class TestGet:
    def test_returns_value(self):
        """get returns the value for a known key."""
        with patch("pi_loop.config_file.load_config", return_value=dict(DEFAULTS)):
            assert get("INFINITE_LOOP_TIMEOUT") == "600"

    def test_returns_default_for_missing(self):
        """get returns default for unknown keys."""
        with patch("pi_loop.config_file.load_config", return_value=dict(DEFAULTS)):
            assert get("NONEXISTENT_KEY") == ""

    def test_custom_value_returned(self):
        """get returns custom stored value."""
        custom = dict(DEFAULTS)
        custom["INFINITE_LOOP_GOAL"] = "my goal"
        with patch("pi_loop.config_file.load_config", return_value=custom):
            assert get("INFINITE_LOOP_GOAL") == "my goal"


class TestGetBool:
    def test_true_values(self):
        """get_bool returns True for 'true', '1', 'yes'."""
        for val in ("true", "True", "1", "yes", "YES"):
            cfg = dict(DEFAULTS)
            cfg["INFINITE_LOOP_RUN"] = val
            with patch("pi_loop.config_file.load_config", return_value=cfg):
                assert get_bool("INFINITE_LOOP_RUN") is True

    def test_false_values(self):
        """get_bool returns False for other values."""
        for val in ("false", "0", "no", "", "maybe"):
            cfg = dict(DEFAULTS)
            cfg["INFINITE_LOOP_RUN"] = val
            with patch("pi_loop.config_file.load_config", return_value=cfg):
                assert get_bool("INFINITE_LOOP_RUN") is False


class TestApplyToEnviron:
    def test_sets_env_vars(self):
        """apply_to_environ sets os.environ defaults."""
        config = {"INFINITE_LOOP_GOAL": "test", "INFINITE_LOOP_RUN": "true"}
        with patch.dict(os.environ, {}, clear=True):
            apply_to_environ(config)
            assert os.environ["INFINITE_LOOP_GOAL"] == "test"
            assert os.environ["INFINITE_LOOP_RUN"] == "true"

    def test_does_not_overwrite_existing(self):
        """apply_to_environ uses setdefault, so existing values are not overwritten."""
        config = {"INFINITE_LOOP_GOAL": "new_value", "INFINITE_LOOP_RUN": "true"}
        with patch.dict(os.environ, {"INFINITE_LOOP_GOAL": "existing_value"}, clear=True):
            apply_to_environ(config)
            assert os.environ["INFINITE_LOOP_GOAL"] == "existing_value"

    def test_uses_load_config_when_no_arg(self):
        """apply_to_environ calls load_config() when config arg is None."""
        custom_cfg = dict(DEFAULTS)
        custom_cfg["INFINITE_LOOP_RUN"] = "true"
        with patch("pi_loop.config_file.load_config", return_value=custom_cfg), patch.dict(os.environ, {}, clear=True):
            apply_to_environ()
            assert os.environ.get("INFINITE_LOOP_RUN") == "true"
