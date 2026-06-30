"""Structured event emitter for omp-loop daemon.

Provides ``emit_event()`` which writes NDJSON lines with the ``[EVENT]``
prefix so that ``LoopManager._parse_daemon_line()`` can triage them
directly instead of reverse-engineering human-readable log strings.

This is an **additive** layer — existing human-readable ``print()`` calls
are left in place.  The ``[EVENT]`` prefix is chosen so it can be detected
with a simple ``str.startswith()`` check, avoiding the need for ANSI-strip
or regex on the structured path.
"""

import json
import sys
from typing import Any


def emit_event(event_type: str, **kwargs: Any) -> None:
    """Emit a structured NDJSON event that the web UI can consume directly.

    Human-readable output is still printed separately — this is additive.
    The ``[EVENT]`` prefix lets ``LoopManager._parse_daemon_line()``
    triage quickly with a simple ``text.startswith("[EVENT] ")`` check
    instead of ANSI-strip + regex.

    Parameters
    ----------
    event_type:
        Machine-readable event type (e.g. ``"spawn"``, ``"worker_response"``,
        ``"iteration_start"``, ``"heartbeat"``, ``"error_type"``, ``"term"``).
    **kwargs:
        Key-value pairs that will be serialised as JSON fields alongside
        ``"type"``.  Values must be JSON-serialisable or have a ``__str__``
        method (``default=str`` is passed to ``json.dumps``).
    """
    event: dict[str, Any] = {"type": event_type}
    event.update(kwargs)
    line = f"[EVENT] {json.dumps(event, default=str)}\n"
    sys.stdout.write(line)
    sys.stdout.flush()
