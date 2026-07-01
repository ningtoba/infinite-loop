"""Unit tests for web_app.rate_limiter — SlidingWindowRateLimiter.

These are the first dedicated web_app unit tests. The rate limiter is
self-contained async logic with no mocking required.
"""
import asyncio

import pytest

from web_app.rate_limiter import SlidingWindowRateLimiter


class TestSlidingWindowRateLimiter:
    """Comprehensive tests for SlidingWindowRateLimiter."""

    @pytest.mark.asyncio
    async def test_basic_allow(self):
        """A single request should be allowed."""
        limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60.0)
        assert await limiter.check("client-a") is True

    @pytest.mark.asyncio
    async def test_allow_up_to_limit(self):
        """Requests up to max_requests should be allowed."""
        limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=60.0)
        for _ in range(3):
            assert await limiter.check("client-a") is True

    @pytest.mark.asyncio
    async def test_deny_after_limit(self):
        """Requests beyond max_requests should be denied."""
        limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60.0)
        assert await limiter.check("client-a") is True
        assert await limiter.check("client-a") is True
        assert await limiter.check("client-a") is False

    @pytest.mark.asyncio
    async def test_per_ip_isolation(self):
        """Different IPs should have independent counters."""
        limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60.0)
        # Exhaust client-a
        assert await limiter.check("client-a") is True
        assert await limiter.check("client-a") is True
        assert await limiter.check("client-a") is False
        # client-b should still be allowed
        assert await limiter.check("client-b") is True
        assert await limiter.check("client-b") is True
        assert await limiter.check("client-b") is False

    @pytest.mark.asyncio
    async def test_window_expiry(self):
        """Expired entries should be trimmed, allowing new requests."""
        limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=0.2)
        assert await limiter.check("client-a") is True
        assert await limiter.check("client-a") is True
        assert await limiter.check("client-a") is False  # Over limit
        await asyncio.sleep(0.25)  # Wait for window to expire
        assert await limiter.check("client-a") is True  # Should be allowed again

    @pytest.mark.asyncio
    async def test_remaining_counts_down(self):
        """remaining() should reflect available capacity."""
        limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60.0)
        assert await limiter.remaining("client-a") == 5
        await limiter.check("client-a")
        assert await limiter.remaining("client-a") == 4
        await limiter.check("client-a")
        assert await limiter.remaining("client-a") == 3

    @pytest.mark.asyncio
    async def test_remaining_zero_when_blocked(self):
        """remaining() should be 0 when limit is reached."""
        limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60.0)
        assert await limiter.check("client-a") is True
        assert await limiter.check("client-a") is True
        assert await limiter.remaining("client-a") == 0

    @pytest.mark.asyncio
    async def test_reset_single_ip(self):
        """reset(ip) should clear that IP's entries only."""
        limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60.0)
        assert await limiter.check("client-a") is True
        assert await limiter.check("client-a") is True
        assert await limiter.check("client-a") is False
        assert await limiter.check("client-b") is True  # Other IP unaffected
        await limiter.reset("client-a")
        assert await limiter.check("client-a") is True  # Reset should allow
        assert await limiter.remaining("client-b") == 1  # Other IP unchanged

    @pytest.mark.asyncio
    async def test_reset_all(self):
        """reset() without args should clear all entries."""
        limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=60.0)
        assert await limiter.check("client-a") is True
        assert await limiter.check("client-b") is True
        assert await limiter.check("client-a") is False
        assert await limiter.check("client-b") is False
        await limiter.reset()
        assert await limiter.check("client-a") is True  # Both should reset
        assert await limiter.check("client-b") is True

    @pytest.mark.asyncio
    async def test_concurrent_safety(self):
        """Concurrent checks from different IPs should not interfere."""
        limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60.0)
        ips = [f"client-{i}" for i in range(10)]

        async def check_ip(ip: str) -> bool:
            return await limiter.check(ip)

        results = await asyncio.gather(*[check_ip(ip) for ip in ips])
        assert all(results)  # All should be allowed (1 req each, limit 5)

    @pytest.mark.asyncio
    async def test_window_slide(self):
        """Oldest entries should slide out as window progresses."""
        limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=0.3)
        # Add 3 at t=0
        assert await limiter.check("client-a") is True
        assert await limiter.check("client-a") is True
        assert await limiter.check("client-a") is True
        assert await limiter.check("client-a") is False  # Over limit
        await asyncio.sleep(0.1)
        # Still blocked — only 0.1s elapsed, 0.2s remaining
        assert await limiter.check("client-a") is False
        await asyncio.sleep(0.25)
        # Window should have slid enough (0.35s total > 0.3s window)
        assert await limiter.check("client-a") is True

    @pytest.mark.asyncio
    async def test_blocked_request_not_counted(self):
        """A denied request should NOT increment the counter."""
        limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=60.0)
        assert await limiter.check("client-a") is True
        assert await limiter.check("client-a") is False  # Denied
        assert await limiter.remaining("client-a") == 0  # Still 0, not -1

    @pytest.mark.asyncio
    async def test_zero_max_requests(self):
        """max_requests=0 should block everything."""
        limiter = SlidingWindowRateLimiter(max_requests=0, window_seconds=60.0)
        assert await limiter.check("client-a") is False
        assert await limiter.remaining("client-a") == 0

    @pytest.mark.asyncio
    async def test_large_window(self):
        """A large window should not cause performance issues."""
        limiter = SlidingWindowRateLimiter(max_requests=100, window_seconds=3600.0)
        for i in range(50):
            assert await limiter.check(f"client-{i}") is True

    @pytest.mark.asyncio
    async def test_remaining_after_window_expiry(self):
        """remaining() should recover after window expiry."""
        limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=0.2)
        assert await limiter.check("client-a") is True
        assert await limiter.check("client-a") is True
        assert await limiter.remaining("client-a") == 0
        await asyncio.sleep(0.25)
        assert await limiter.remaining("client-a") == 2  # Full capacity restored
