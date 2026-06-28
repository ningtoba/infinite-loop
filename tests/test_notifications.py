"""Tests for notifications.py — desktop, Pushbullet, ntfy notifications."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch


from hermes_loop.notifications import (
    _send_desktop_notification,
    _pushbullet_notify,
    _ntfy_notify,
    _send_per_iteration_notifications,
    _send_completion_notification,
)

# ===================================================================
# _send_desktop_notification tests
# ===================================================================


class TestSendDesktopNotification:
    """Tests for _send_desktop_notification — notify-send."""

    def test_notify_bin_not_found(self):
        """When notify-send is not found, silently return."""
        with patch("hermes_loop.notifications.shutil.which", return_value=None):
            _send_desktop_notification("test summary", 30.0)

    def test_sends_notification(self):
        """Basic notification with summary and duration."""
        with (
            patch(
                "hermes_loop.notifications.shutil.which",
                return_value="/usr/bin/notify-send",
            ),
            patch("hermes_loop.notifications.subprocess.run") as mock_run,
        ):
            _send_desktop_notification("Test summary", 30.0)

        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert args[0][0] == "/usr/bin/notify-send"
        assert args[0][1] == "--"
        assert args[0][2] == "Infinite Loop"
        assert "Test summary" in args[0][3]
        assert "(30s)" in args[0][3]

    def test_with_error(self):
        """Notification includes error text if provided."""
        with (
            patch(
                "hermes_loop.notifications.shutil.which",
                return_value="/usr/bin/notify-send",
            ),
            patch("hermes_loop.notifications.subprocess.run") as mock_run,
        ):
            _send_desktop_notification("Test summary", 10.0, error="Something broke")

        args = mock_run.call_args[0][0]
        body = args[3]
        assert "⚠" in body
        assert "Something broke" in body

    def test_body_truncated_to_120_chars(self):
        """Body is truncated to 120 chars."""
        long_summary = "x" * 200
        with (
            patch(
                "hermes_loop.notifications.shutil.which",
                return_value="/usr/bin/notify-send",
            ),
            patch("hermes_loop.notifications.subprocess.run") as mock_run,
        ):
            _send_desktop_notification(long_summary)

        args = mock_run.call_args[0][0]
        body = args[3]
        assert len(body) <= 120

    def test_without_duration(self):
        """Without duration, duration is omitted from body."""
        with (
            patch(
                "hermes_loop.notifications.shutil.which",
                return_value="/usr/bin/notify-send",
            ),
            patch("hermes_loop.notifications.subprocess.run") as mock_run,
        ):
            _send_desktop_notification("Test summary", duration=0)

        args = mock_run.call_args[0][0]
        # No "(0s)" appended
        assert "(0s)" not in args[3]

    def test_error_truncated_to_60_chars(self):
        """Error text is truncated to 60 chars."""
        long_error = "e" * 200
        with (
            patch(
                "hermes_loop.notifications.shutil.which",
                return_value="/usr/bin/notify-send",
            ),
            patch("hermes_loop.notifications.subprocess.run") as mock_run,
        ):
            _send_desktop_notification("summary", 10.0, error=long_error)

        args = mock_run.call_args[0][0]
        body = args[3]
        # " ⚠ " = 2 chars + 60 chars error
        assert "⚠" in body

    def test_timeout_expired_handled(self):
        """subprocess.TimeoutExpired is handled gracefully."""
        with (
            patch(
                "hermes_loop.notifications.shutil.which",
                return_value="/usr/bin/notify-send",
            ),
            patch(
                "hermes_loop.notifications.subprocess.run",
                side_effect=TimeoutError("timed out"),
            ),
        ):
            _send_desktop_notification("test")  # should not raise

    def test_oserror_handled(self):
        """OSError is handled gracefully."""
        with (
            patch(
                "hermes_loop.notifications.shutil.which",
                return_value="/usr/bin/notify-send",
            ),
            patch(
                "hermes_loop.notifications.subprocess.run",
                side_effect=OSError("permission denied"),
            ),
        ):
            _send_desktop_notification("test")  # should not raise


# ===================================================================
# _pushbullet_notify tests
# ===================================================================


class TestPushbulletNotify:
    """Tests for _pushbullet_notify — Pushbullet API v2."""

    def test_empty_token_returns_false(self):
        """Empty API token returns False."""
        assert _pushbullet_notify("", "title", "body") is False

    def test_successful_send(self):
        """Successful API call returns True."""
        mock_response = MagicMock()
        mock_response.__enter__.return_value.status = 200

        with patch(
            "hermes_loop.notifications.urllib.request.urlopen",
            return_value=mock_response,
        ):
            result = _pushbullet_notify("valid_token", "Test Title", "Test Body")

        assert result is True

    def test_request_construction(self):
        """Request is constructed correctly."""
        mock_response = MagicMock()
        mock_response.__enter__.return_value.status = 200

        with (
            patch(
                "hermes_loop.notifications.urllib.request.urlopen",
                return_value=mock_response,
            ),
            patch("hermes_loop.notifications.urllib.request.Request") as mock_request,
        ):
            _pushbullet_notify("token123", "Test Title", "Test Body")

        mock_request.assert_called_once()
        call_args, call_kwargs = mock_request.call_args
        assert call_args[0] == "https://api.pushbullet.com/v2/pushes"
        assert call_kwargs["method"] == "POST"
        assert call_kwargs["headers"]["Access-Token"] == "token123"

    def test_payload_content(self):
        """Payload contains correct fields with truncation."""
        mock_response = MagicMock()
        mock_response.status = 200

        with (
            patch(
                "hermes_loop.notifications.urllib.request.urlopen",
                return_value=mock_response,
            ),
            patch("hermes_loop.notifications.urllib.request.Request") as mock_request,
        ):
            _pushbullet_notify("token", "Test Title", "Test Body")

        # Extract the data payload
        call_args, call_kwargs = mock_request.call_args
        payload = json.loads(call_kwargs["data"])
        assert payload["type"] == "note"
        assert payload["title"] == "Test Title"
        assert payload["body"] == "Test Body"

    def test_title_truncated_to_256(self):
        """Title is truncated to 256 chars."""
        long_title = "t" * 500
        mock_response = MagicMock()
        mock_response.status = 200

        with (
            patch(
                "hermes_loop.notifications.urllib.request.urlopen",
                return_value=mock_response,
            ),
            patch("hermes_loop.notifications.urllib.request.Request") as mock_request,
        ):
            _pushbullet_notify("token", long_title, "body")

        call_args, call_kwargs = mock_request.call_args
        payload = json.loads(call_kwargs["data"])
        assert len(payload["title"]) <= 256

    def test_body_truncated_to_4096(self):
        """Body is truncated to 4096 chars."""
        long_body = "b" * 5000
        mock_response = MagicMock()
        mock_response.status = 200

        with (
            patch(
                "hermes_loop.notifications.urllib.request.urlopen",
                return_value=mock_response,
            ),
            patch("hermes_loop.notifications.urllib.request.Request") as mock_request,
        ):
            _pushbullet_notify("token", "title", long_body)

        call_args, call_kwargs = mock_request.call_args
        payload = json.loads(call_kwargs["data"])
        assert len(payload["body"]) <= 4096

    def test_urlerror_handled(self):
        """URLError is handled gracefully."""
        with (
            patch(
                "hermes_loop.notifications.urllib.request.urlopen",
                side_effect=TimeoutError("timed out"),
            ),
        ):
            result = _pushbullet_notify("token", "title", "body")
        assert result is False

    def test_connection_error_handled(self):
        """ConnectionError is handled gracefully."""
        with (
            patch(
                "hermes_loop.notifications.urllib.request.urlopen",
                side_effect=ConnectionError("refused"),
            ),
        ):
            result = _pushbullet_notify("token", "title", "body")
        assert result is False

    def test_non_200_status(self):
        """Non-200 status might still return True (checks status==200)."""
        mock_response = MagicMock()
        mock_response.status = 400

        with patch(
            "hermes_loop.notifications.urllib.request.urlopen",
            return_value=mock_response,
        ):
            result = _pushbullet_notify("token", "title", "body")
        assert result is False


# ===================================================================
# _ntfy_notify tests
# ===================================================================


class TestNtfyNotify:
    """Tests for _ntfy_notify — ntfy.sh push notifications."""

    def test_empty_topic_returns_false(self):
        """Empty topic returns False."""
        assert _ntfy_notify("", "title", "body") is False

    def test_topic_with_only_whitespace(self):
        """Whitespace-only topic returns False after stripping."""
        assert _ntfy_notify("  ", "title", "body") is False

    def test_topic_stripped(self):
        """Topic is stripped of leading/trailing whitespace and slashes."""
        mock_response = MagicMock()
        mock_response.__enter__.return_value.status = 200

        with patch(
            "hermes_loop.notifications.urllib.request.urlopen",
            return_value=mock_response,
        ):
            result = _ntfy_notify(" /mytopic/ ", "title", "body")
        assert result is True

    def test_successful_send(self):
        """Successful API call returns True."""
        mock_response = MagicMock()
        mock_response.__enter__.return_value.status = 200

        with patch(
            "hermes_loop.notifications.urllib.request.urlopen",
            return_value=mock_response,
        ):
            result = _ntfy_notify("mytopic", "Test Title", "Test Body")
        assert result is True

    def test_request_construction(self):
        """Request is constructed correctly with PUT method."""
        mock_response = MagicMock()
        mock_response.__enter__.return_value.status = 200

        with (
            patch(
                "hermes_loop.notifications.urllib.request.urlopen",
                return_value=mock_response,
            ),
            patch("hermes_loop.notifications.urllib.request.Request") as mock_request,
        ):
            _ntfy_notify("mytopic", "Test Title", "Test Body")

        mock_request.assert_called_once()
        call_args, call_kwargs = mock_request.call_args
        assert call_args[0] == "https://ntfy.sh/mytopic"
        assert call_kwargs["method"] == "PUT"
        assert call_kwargs["headers"]["Title"] == "Test Title"
        assert call_kwargs["headers"]["Content-Type"] == "text/plain; charset=utf-8"

    def test_custom_server(self):
        """Custom server URL is used correctly."""
        mock_response = MagicMock()
        mock_response.status = 200

        with (
            patch(
                "hermes_loop.notifications.urllib.request.urlopen",
                return_value=mock_response,
            ),
            patch("hermes_loop.notifications.urllib.request.Request") as mock_request,
        ):
            _ntfy_notify("mytopic", "title", "body", server="https://ntfy.example.com")

        call_args, _ = mock_request.call_args
        assert call_args[0] == "https://ntfy.example.com/mytopic"

    def test_title_truncated_to_256(self):
        """Title header is truncated to 256 chars."""
        long_title = "t" * 500
        mock_response = MagicMock()
        mock_response.status = 200

        with (
            patch(
                "hermes_loop.notifications.urllib.request.urlopen",
                return_value=mock_response,
            ),
            patch("hermes_loop.notifications.urllib.request.Request") as mock_request,
        ):
            _ntfy_notify("mytopic", long_title, "body")

        _, call_kwargs = mock_request.call_args
        assert len(call_kwargs["headers"]["Title"]) <= 256

    def test_body_truncated_to_4096(self):
        """Body is truncated to 4096 chars."""
        long_body = "b" * 5000
        mock_response = MagicMock()
        mock_response.status = 200

        with (
            patch(
                "hermes_loop.notifications.urllib.request.urlopen",
                return_value=mock_response,
            ),
            patch("hermes_loop.notifications.urllib.request.Request") as mock_request,
        ):
            _ntfy_notify("mytopic", "title", long_body)

        _, call_kwargs = mock_request.call_args
        assert len(call_kwargs["data"]) <= 4096

    def test_urlerror_handled(self):
        """URLError is handled gracefully."""
        with (
            patch(
                "hermes_loop.notifications.urllib.request.urlopen",
                side_effect=TimeoutError("timed out"),
            ),
        ):
            result = _ntfy_notify("mytopic", "title", "body")
        assert result is False

    def test_oserror_handled(self):
        """OSError is handled gracefully."""
        with (
            patch(
                "hermes_loop.notifications.urllib.request.urlopen",
                side_effect=OSError("connection reset"),
            ),
        ):
            result = _ntfy_notify("mytopic", "title", "body")
        assert result is False

    def test_non_200_status(self):
        """Non-200 status returns False."""
        mock_response = MagicMock()
        mock_response.status = 404

        with patch(
            "hermes_loop.notifications.urllib.request.urlopen",
            return_value=mock_response,
        ):
            result = _ntfy_notify("mytopic", "title", "body")
        assert result is False


# ===================================================================
# _send_per_iteration_notifications tests
# ===================================================================


class TestSendPerIterationNotifications:
    """Tests for _send_per_iteration_notifications — dispatches to all channels."""

    def test_desktop_only(self):
        """When only desktop is enabled, only desktop is called."""
        with (
            patch(
                "hermes_loop.notifications._send_desktop_notification"
            ) as mock_desktop,
            patch("hermes_loop.notifications._pushbullet_notify") as mock_pb,
            patch("hermes_loop.notifications._ntfy_notify") as mock_ntfy,
        ):
            _send_per_iteration_notifications(
                summary="test",
                duration=10.0,
                error=None,
                notify_desktop_enabled=True,
                notify_pushbullet="",
                notify_ntfy="",
                notify_ntfy_server="https://ntfy.sh",
            )

        mock_desktop.assert_called_once_with("test", 10.0, None)
        mock_pb.assert_not_called()
        mock_ntfy.assert_not_called()

    def test_pushbullet_only(self):
        """When only pushbullet is configured."""
        with (
            patch("hermes_loop.notifications._send_desktop_notification"),
            patch("hermes_loop.notifications._pushbullet_notify") as mock_pb,
            patch("hermes_loop.notifications._ntfy_notify"),
        ):
            _send_per_iteration_notifications(
                summary="test",
                duration=10.0,
                error=None,
                notify_desktop_enabled=False,
                notify_pushbullet="pb_token",
                notify_ntfy="",
                notify_ntfy_server="https://ntfy.sh",
            )

        mock_pb.assert_called_once()
        args, _ = mock_pb.call_args
        assert args[0] == "pb_token"
        assert "Iteration" in args[1]

    def test_all_channels(self):
        """All channels called when configured."""
        with (
            patch(
                "hermes_loop.notifications._send_desktop_notification"
            ) as mock_desktop,
            patch("hermes_loop.notifications._pushbullet_notify") as mock_pb,
            patch("hermes_loop.notifications._ntfy_notify") as mock_ntfy,
        ):
            _send_per_iteration_notifications(
                summary="test",
                duration=10.0,
                error="error msg",
                notify_desktop_enabled=True,
                notify_pushbullet="pb_token",
                notify_ntfy="ntfy_topic",
                notify_ntfy_server="https://ntfy.sh",
            )

        mock_desktop.assert_called_once_with("test", 10.0, "error msg")
        mock_pb.assert_called_once()
        mock_ntfy.assert_called_once()

    def test_body_includes_duration_and_error(self):
        """PB and ntfy body includes duration and error."""
        with (
            patch("hermes_loop.notifications._send_desktop_notification"),
            patch("hermes_loop.notifications._pushbullet_notify") as mock_pb,
            patch("hermes_loop.notifications._ntfy_notify"),
        ):
            _send_per_iteration_notifications(
                summary="test summary",
                duration=30.5,
                error="some error",
                notify_desktop_enabled=False,
                notify_pushbullet="token",
                notify_ntfy="",
                notify_ntfy_server="https://ntfy.sh",
            )

        args, _ = mock_pb.call_args
        body = args[2]
        assert "(30s)" in body  # 30.5 → "30s" with :.0f (round-half-even)
        assert "⚠" in body
        assert "some error" in body

    def test_body_truncated_to_200(self):
        """Summary body is truncated to 200 chars."""
        long_summary = "x" * 300
        with (
            patch("hermes_loop.notifications._send_desktop_notification"),
            patch("hermes_loop.notifications._pushbullet_notify") as mock_pb,
            patch("hermes_loop.notifications._ntfy_notify"),
        ):
            _send_per_iteration_notifications(
                summary=long_summary,
                duration=0,
                error=None,
                notify_desktop_enabled=False,
                notify_pushbullet="token",
                notify_ntfy="",
                notify_ntfy_server="https://ntfy.sh",
            )

        args, _ = mock_pb.call_args
        # title is "Infinite Loop Iteration", body is summary[:200]
        assert len(args[2]) <= 200

    def test_no_channels(self):
        """No channels configured — no calls."""
        with (
            patch(
                "hermes_loop.notifications._send_desktop_notification"
            ) as mock_desktop,
            patch("hermes_loop.notifications._pushbullet_notify") as mock_pb,
            patch("hermes_loop.notifications._ntfy_notify") as mock_ntfy,
        ):
            _send_per_iteration_notifications(
                summary="test",
                duration=10.0,
                error=None,
                notify_desktop_enabled=False,
                notify_pushbullet="",
                notify_ntfy="",
                notify_ntfy_server="https://ntfy.sh",
            )

        mock_desktop.assert_not_called()
        mock_pb.assert_not_called()
        mock_ntfy.assert_not_called()


# ===================================================================
# _send_completion_notification tests
# ===================================================================


class TestSendCompletionNotification:
    """Tests for _send_completion_notification — final summary."""

    def test_empty_state_returns_early(self):
        """Empty state returns early without sending anything."""
        with (
            patch("hermes_loop.notifications.shutil.which") as mock_which,
            patch("hermes_loop.notifications._pushbullet_notify") as mock_pb,
            patch("hermes_loop.notifications._ntfy_notify") as mock_ntfy,
        ):
            _send_completion_notification({})
        mock_which.assert_not_called()
        mock_pb.assert_not_called()
        mock_ntfy.assert_not_called()

    def test_sends_desktop_notification(self):
        """Sends desktop notification via notify-send."""
        state = {
            "stats": {
                "success_count": 5,
                "error_count": 2,
                "total_duration_seconds": 300,
            },
            "total_iterations": 7,
            "status": "completed",
        }

        with (
            patch(
                "hermes_loop.notifications.shutil.which",
                return_value="/usr/bin/notify-send",
            ),
            patch("hermes_loop.notifications.subprocess.run") as mock_run,
        ):
            _send_completion_notification(state)

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[2] == "Infinite Loop Complete"

    def test_desktop_message_content(self):
        """Desktop message includes stats."""
        state = {
            "stats": {
                "success_count": 5,
                "error_count": 2,
                "total_duration_seconds": 300,
            },
            "total_iterations": 7,
            "status": "completed",
        }

        with (
            patch(
                "hermes_loop.notifications.shutil.which",
                return_value="/usr/bin/notify-send",
            ),
            patch("hermes_loop.notifications.subprocess.run") as mock_run,
        ):
            _send_completion_notification(state)

        args = mock_run.call_args[0][0]
        msg = args[3]
        assert "completed" in msg
        assert "7" in msg
        assert "5" in msg
        assert "2" in msg

    def test_desktop_notify_not_found(self):
        """When notify-send not found, skip desktop."""
        state = {
            "stats": {},
            "total_iterations": 0,
            "status": "running",
        }

        with (
            patch("hermes_loop.notifications.shutil.which", return_value=None),
            patch("hermes_loop.notifications.subprocess.run") as mock_run,
            patch("hermes_loop.notifications._pushbullet_notify"),
            patch("hermes_loop.notifications._ntfy_notify"),
        ):
            _send_completion_notification(state)

        mock_run.assert_not_called()

    def test_sends_pushbullet(self):
        """Sends pushbullet notification when token provided."""
        state = {
            "stats": {
                "success_count": 3,
                "error_count": 1,
                "total_duration_seconds": 120,
            },
            "total_iterations": 4,
            "status": "completed",
        }

        with (
            patch("hermes_loop.notifications.shutil.which", return_value=None),
            patch("hermes_loop.notifications._pushbullet_notify") as mock_pb,
            patch("hermes_loop.notifications._ntfy_notify"),
        ):
            _send_completion_notification(state, notify_pushbullet="token")

        mock_pb.assert_called_once()
        args, _ = mock_pb.call_args
        assert args[0] == "token"
        assert "Complete" in args[1]

    def test_sends_ntfy(self):
        """Sends ntfy notification when topic provided."""
        state = {
            "stats": {
                "success_count": 3,
                "error_count": 1,
                "total_duration_seconds": 120,
            },
            "total_iterations": 4,
            "status": "completed",
        }

        with (
            patch("hermes_loop.notifications.shutil.which", return_value=None),
            patch("hermes_loop.notifications._pushbullet_notify"),
            patch("hermes_loop.notifications._ntfy_notify") as mock_ntfy,
        ):
            _send_completion_notification(
                state,
                notify_ntfy="mytopic",
                notify_ntfy_server="https://ntfy.example.com",
            )

        mock_ntfy.assert_called_once()
        args, _ = mock_ntfy.call_args
        assert args[0] == "mytopic"
        assert "Complete" in args[1]
        assert args[3] == "https://ntfy.example.com"

    def test_all_channels_completion(self):
        """All channels are called for completion."""
        state = {
            "stats": {
                "success_count": 5,
                "error_count": 0,
                "total_duration_seconds": 300,
            },
            "total_iterations": 5,
            "status": "completed",
        }

        with (
            patch(
                "hermes_loop.notifications.shutil.which",
                return_value="/usr/bin/notify-send",
            ),
            patch("hermes_loop.notifications.subprocess.run"),
            patch("hermes_loop.notifications._pushbullet_notify") as mock_pb,
            patch("hermes_loop.notifications._ntfy_notify") as mock_ntfy,
        ):
            _send_completion_notification(
                state,
                notify_pushbullet="pb_token",
                notify_ntfy="ntfy_topic",
                notify_ntfy_server="https://ntfy.sh",
            )

        mock_pb.assert_called_once()
        mock_ntfy.assert_called_once()

    def test_desktop_timeout_handled(self):
        """Desktop subprocess timeout doesn't crash."""
        state = {
            "stats": {},
            "total_iterations": 0,
            "status": "running",
        }

        with (
            patch(
                "hermes_loop.notifications.shutil.which",
                return_value="/usr/bin/notify-send",
            ),
            patch(
                "hermes_loop.notifications.subprocess.run",
                side_effect=TimeoutError("timed out"),
            ),
        ):
            _send_completion_notification(state)  # should not raise

    def test_default_values(self):
        """Default values for optional params work."""
        state = {
            "stats": {
                "success_count": 0,
                "error_count": 0,
                "total_duration_seconds": 0,
            },
            "total_iterations": 0,
            "status": "unknown",
        }

        with (
            patch("hermes_loop.notifications.shutil.which", return_value=None),
            patch("hermes_loop.notifications._pushbullet_notify") as mock_pb,
            patch("hermes_loop.notifications._ntfy_notify") as mock_ntfy,
        ):
            _send_completion_notification(state)

        mock_pb.assert_not_called()
        mock_ntfy.assert_not_called()
