"""Sliding-window rate limiter using asyncio for the pi-loop web API."""

import asyncio
import logging
import time
from collections import defaultdict

logger = logging.getLogger(__name__)


class SlidingWindowRateLimiter:
    """Per-IP sliding-window rate limiter.

    Tracks request timestamps per client IP. On each check, expired
    entries (outside the sliding window) are trimmed before counting.
    Thread-safe via an asyncio lock.

    Example::

        limiter = SlidingWindowRateLimiter(max_requests=30, window_seconds=60)
        allowed = await limiter.check(client_ip)
    """

    def __init__(self, max_requests: int, window_seconds: float = 60.0) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._entries: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def check(self, ip: str) -> bool:
        """Check if *ip* has exceeded the rate limit.

        Returns True if the request is allowed, False if rate-limited.
        The timestamp for this request is *only* recorded when True is
        returned, so a blocked request does not count toward the limit.
        """
        now = time.monotonic()
        cutoff = now - self.window_seconds

        async with self._lock:
            timestamps = self._entries[ip]
            # Trim expired entries from the front
            while timestamps and timestamps[0] < cutoff:
                timestamps.pop(0)

            if len(timestamps) >= self.max_requests:
                return False

            timestamps.append(now)
            return True

    async def remaining(self, ip: str) -> int:
        """Return how many requests *ip* can still make in this window."""
        now = time.monotonic()
        cutoff = now - self.window_seconds

        async with self._lock:
            timestamps = self._entries.get(ip, [])
            while timestamps and timestamps[0] < cutoff:
                timestamps.pop(0)
            return max(0, self.max_requests - len(timestamps))

    async def reset(self, ip: str | None = None) -> None:
        """Clear stored entries, optionally for a single *ip* only."""
        async with self._lock:
            if ip is not None:
                self._entries.pop(ip, None)
            else:
                self._entries.clear()
