"""Tests for omp_loop.config constants."""

from omp_loop import config


def test_version_exists():
    """VERSION is a non-empty string."""
    assert isinstance(config.VERSION, str)
    assert len(config.VERSION) > 0


def test_version_format():
    """VERSION follows semver pattern (at least X.Y.Z)."""
    parts = config.VERSION.split(".")
    assert len(parts) >= 3
    for part in parts:
        # Each segment should be digits (possibly with pre-release suffix)
        assert part  # not empty


def test_ledger_path_exists():
    """LEDGER_PATH is a non-empty string."""
    assert isinstance(config.LEDGER_PATH, str)
    assert len(config.LEDGER_PATH) > 0
    assert config.LEDGER_PATH.startswith("/")


def test_ledger_path_is_tmp():
    """LEDGER_PATH is under /tmp."""
    assert config.LEDGER_PATH.startswith("/tmp/")


def test_lock_path_exists():
    """LOCK_PATH is a non-empty string."""
    assert isinstance(config.LOCK_PATH, str)
    assert len(config.LOCK_PATH) > 0
    assert config.LOCK_PATH.startswith("/tmp/")


def test_sentinel_path_default():
    """SENTINEL_PATH_DEFAULT is a non-empty string."""
    assert isinstance(config.SENTINEL_PATH_DEFAULT, str)
    assert len(config.SENTINEL_PATH_DEFAULT) > 0
    assert config.SENTINEL_PATH_DEFAULT.startswith("/tmp/")


def test_status_file_default():
    """STATUS_FILE_DEFAULT is an empty string."""
    assert config.STATUS_FILE_DEFAULT == ""


def test_log_format():
    """LOG_FORMAT is a non-empty string with expected placeholders."""
    assert isinstance(config.LOG_FORMAT, str)
    assert "%(asctime)s" in config.LOG_FORMAT
    assert "%(levelname)s" in config.LOG_FORMAT
    assert "%(message)s" in config.LOG_FORMAT


def test_log_date_format():
    """LOG_DATE_FORMAT is a non-empty string."""
    assert isinstance(config.LOG_DATE_FORMAT, str)
    assert len(config.LOG_DATE_FORMAT) > 0


def test_convergence_window_default():
    """DEFAULT_CONVERGENCE_WINDOW is a positive integer."""
    assert isinstance(config.DEFAULT_CONVERGENCE_WINDOW, int)
    assert config.DEFAULT_CONVERGENCE_WINDOW > 0
    assert config.DEFAULT_CONVERGENCE_WINDOW == 5


def test_convergence_threshold_default():
    """DEFAULT_CONVERGENCE_THRESHOLD is a float between 0 and 1."""
    assert isinstance(config.DEFAULT_CONVERGENCE_THRESHOLD, float)
    assert 0 < config.DEFAULT_CONVERGENCE_THRESHOLD <= 1
    assert config.DEFAULT_CONVERGENCE_THRESHOLD == 0.9


def test_base_toolsets():
    """BASE_TOOLSETS is a non-empty string with comma-separated tools."""
    assert isinstance(config.BASE_TOOLSETS, str)
    assert len(config.BASE_TOOLSETS) > 0
    toolsets = config.BASE_TOOLSETS.split(",")
    assert len(toolsets) > 1
    assert "terminal" in toolsets
    assert "file" in toolsets


def test_heartbeat_dir():
    """HEARTBEAT_DIR defaults to _get_data_dir()."""
    assert config._get_data_dir() == config.HEARTBEAT_DIR


def test_heartbeat_interval():
    """HEARTBEAT_INTERVAL is a positive integer."""
    assert isinstance(config.HEARTBEAT_INTERVAL, int)
    assert config.HEARTBEAT_INTERVAL > 0


def test_heartbeat_prefix():
    """HEARTBEAT_PREFIX is a non-empty string."""
    assert isinstance(config.HEARTBEAT_PREFIX, str)
    assert len(config.HEARTBEAT_PREFIX) > 0


def test_error_severity():
    """_ERROR_SEVERITY maps known error types to severity integers."""
    severity = config._ERROR_SEVERITY
    assert isinstance(severity, dict)
    for key in ("timeout", "network", "schema", "unknown", "heartbeat"):
        assert key in severity
        assert isinstance(severity[key], int)


def test_error_thresholds():
    """_ERROR_THRESHOLDS maps error types to threshold dicts."""
    thresholds = config._ERROR_THRESHOLDS
    assert isinstance(thresholds, dict)
    for key in ("timeout", "network", "schema", "unknown", "heartbeat"):
        assert key in thresholds
        t = thresholds[key]
        assert "mild" in t
        assert "stop" in t


def test_task_patterns():
    """TASK_PATTERNS is a non-empty dict with expected keys."""
    patterns = config.TASK_PATTERNS
    assert isinstance(patterns, dict)
    assert len(patterns) > 0
    for key in ("research", "code-fix", "code-build"):
        assert key in patterns
        assert "keywords" in patterns[key]
        assert "extra_toolsets" in patterns[key]
        assert "description" in patterns[key]
        assert isinstance(patterns[key]["keywords"], list)
        assert len(patterns[key]["keywords"]) > 0
