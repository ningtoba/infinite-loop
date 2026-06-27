"""Notification utilities — desktop, Pushbullet, and ntfy notifications."""

import json
import shutil
import subprocess
import urllib.error
import urllib.request

from .file_utils import _log


def _send_desktop_notification(
    summary: str, duration: float = 0, error: str | None = None
):
    """Send a desktop notification via notify-send (Linux only)."""
    notify_bin = shutil.which("notify-send")
    if not notify_bin:
        return
    try:
        title = "Infinite Loop"
        body = summary[:120]
        if duration > 0:
            body += f" ({duration:.0f}s)"
        if error:
            body += f" ⚠ {error[:60]}"
            subprocess.run([notify_bin, "--", title, body], timeout=3)
        else:
            subprocess.run([notify_bin, "--", title, body], timeout=3)
    except (subprocess.TimeoutExpired, OSError):
        pass


def _pushbullet_notify(api_token: str, title: str, body: str) -> bool:
    """Send a push notification via Pushbullet API v2."""
    if not api_token:
        return False
    try:
        payload = json.dumps(
            {
                "type": "note",
                "title": title[:256],
                "body": body[:4096],
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            "https://api.pushbullet.com/v2/pushes",
            data=payload,
            headers={
                "Access-Token": api_token,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        _log(f"[PUSHBULLET] Notification failed: {e}", level="WARN")
        return False


def _ntfy_notify(
    topic: str, title: str, body: str, server: str = "https://ntfy.sh"
) -> bool:
    """Send a push notification via ntfy."""
    if not topic:
        return False
    topic = topic.strip().strip("/")
    if not topic:
        return False
    url = f"{server.rstrip('/')}/{topic}"
    try:
        payload = body[:4096].encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Title": title[:256],
                "Content-Type": "text/plain; charset=utf-8",
                "Priority": "default",
            },
            method="PUT",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError) as e:
        _log(f"[NTFY] Notification failed: {e}", level="WARN")
        return False


def _send_per_iteration_notifications(
    summary: str,
    duration: float,
    error: str | None,
    notify_desktop_enabled: bool,
    notify_pushbullet: str,
    notify_ntfy: str,
    notify_ntfy_server: str,
):
    """Send per-iteration notifications to all configured channels."""
    if notify_desktop_enabled:
        _send_desktop_notification(summary, duration, error)
    title = "Infinite Loop Iteration"
    body = summary[:200]
    if duration > 0:
        body += f" ({duration:.0f}s)"
    if error:
        body += f" ⚠ {error[:100]}"
    if notify_pushbullet:
        _pushbullet_notify(notify_pushbullet, title, body)
    if notify_ntfy:
        _ntfy_notify(notify_ntfy, title, body, notify_ntfy_server)


def _send_completion_notification(
    state: dict,
    notify_pushbullet: str = "",
    notify_ntfy: str = "",
    notify_ntfy_server: str = "https://ntfy.sh",
) -> None:
    """Send a summary notification when the daemon finishes."""
    if not state:
        return
    stats = state.get("stats", {})
    total = state.get("total_iterations", 0)
    status = state.get("status", "unknown")
    msg = (
        f"Status: {status}\n"
        f"Iterations: {total}\n"
        f"Success: {stats.get('success_count', 0)}\n"
        f"Errors: {stats.get('error_count', 0)}\n"
        f"Total time: {stats.get('total_duration_seconds', 0):.0f}s"
    )

    notify_bin = shutil.which("notify-send")
    if notify_bin:
        try:
            subprocess.run([notify_bin, "--", "Infinite Loop Complete", msg], timeout=5)
        except (subprocess.TimeoutExpired, OSError):
            pass

    if notify_pushbullet:
        _pushbullet_notify(notify_pushbullet, "Infinite Loop Complete", msg)

    if notify_ntfy:
        _ntfy_notify(notify_ntfy, "Infinite Loop Complete", msg, notify_ntfy_server)
