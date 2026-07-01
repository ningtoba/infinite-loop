"""Heartbeat helpers (Session Self-Healing)."""

import glob
import logging
import os

from .config import HEARTBEAT_DIR, HEARTBEAT_PREFIX
from .file_utils import _log

logger = logging.getLogger(__name__)


def _cleanup_stale_heartbeats() -> None:
    """Remove heartbeat files from previous daemon instances at startup."""
    pattern = os.path.join(HEARTBEAT_DIR, f"{HEARTBEAT_PREFIX}*")
    removed = 0
    for f in glob.glob(pattern):
        try:
            os.remove(f)
            removed += 1
        except OSError as e:
            logger.debug("Failed to remove stale heartbeat %s: %s", f, e)
    if removed > 0:
        _log(f"[HEARTBEAT] Cleaned up {removed} stale heartbeat file(s)", level="DEBUG")
