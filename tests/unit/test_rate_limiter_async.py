"""
Unit tests for AsyncRateLimiter.
"""

import pytest
import asyncio
import time
from app.utils.rate_limiter import AsyncRateLimiter


class TestAsyncRateLimiter:
    """Test cases for AsyncRateLimiter."""

    @pytest.mark.asyncio
    async def test_basic_acquire(self):
        """Test basic acquire functionality."""
        limiter = AsyncRateLimiter(max_calls=5, time_window_seconds=60)
        
        # Should allow 5 calls
        for i in range(5):
            result = await limiter.acquire(blocking=False)
            assert result is True
        
        # 6th call should be blocked
        result = await limiter.acquire(blocking=False)
        assert result is False

    @pytest.mark.asyncio
    async def test_time_window(self):
        """Test that time window works correctly."""
        limiter = AsyncRateLimiter(max_calls=2, time_window_seconds=1)
        
        # Make 2 calls
        assert await limiter.acquire(blocking=False) is True
        assert await limiter.acquire(blocking=False) is True
        
        # 3rd call should be blocked
        assert await limiter.acquire(blocking=False) is False
        
        # Wait for time window to expire
        await asyncio.sleep(1.1)
        
        # Should allow calls again
        assert await limiter.acquire(blocking=False) is True

    @pytest.mark.asyncio
    async def test_blocking_mode(self):
        """Test blocking mode."""
        limiter = AsyncRateLimiter(max_calls=1, time_window_seconds=1)
        
        # First call should succeed
        assert await limiter.acquire(blocking=True) is True
        
        # Second call should block and wait
        start_time = time.time()
        assert await limiter.acquire(blocking=True) is True
        elapsed = time.time() - start_time
        
        # Should have waited approximately 1 second
        assert 0.9 <= elapsed <= 1.5  # Allow some tolerance

    @pytest.mark.asyncio
    async def test_timeout(self):
        """Test timeout handling."""
        limiter = AsyncRateLimiter(max_calls=1, time_window_seconds=2)
        
        # First call should succeed
        assert await limiter.acquire(blocking=True) is True
        
        # Second call with short timeout should fail
        start_time = time.time()
        result = await limiter.acquire(blocking=True, timeout=0.5)
        elapsed = time.time() - start_time
        
        assert result is False
        assert elapsed < 1.0  # Should return quickly due to timeout

    @pytest.mark.asyncio
    async def test_concurrent_access(self):
        """Test concurrent access from multiple coroutines."""
        limiter = AsyncRateLimiter(max_calls=10, time_window_seconds=60)
        results = []
        
        async def worker():
            for _ in range(5):
                result = await limiter.acquire(blocking=False)
                results.append(result)
        
        # Create multiple coroutines
        tasks = [worker() for _ in range(5)]
        await asyncio.gather(*tasks)
        
        # Should have exactly 10 True results (max_calls)
        assert results.count(True) == 10
        
        # Remaining should be False
        assert results.count(False) == 15  # 5 coroutines * 5 calls - 10 allowed = 15

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test async context manager usage."""
        limiter = AsyncRateLimiter(max_calls=1, time_window_seconds=60)
        
        async with limiter:
            # Should have acquired
            result = await limiter.acquire(blocking=False)
            assert result is False
        
        # After context exit, should be able to acquire again
        limiter2 = AsyncRateLimiter(max_calls=2, time_window_seconds=60)
        async with limiter2:
            pass
        # Should still have 1 slot available
        assert await limiter2.acquire(blocking=False) is True

    @pytest.mark.asyncio
    async def test_multiple_windows(self):
        """Test behavior across multiple time windows."""
        limiter = AsyncRateLimiter(max_calls=2, time_window_seconds=1)
        
        # First window
        assert await limiter.acquire(blocking=False) is True
        assert await limiter.acquire(blocking=False) is True
        assert await limiter.acquire(blocking=False) is False
        
        # Wait for window to expire
        await asyncio.sleep(1.1)
        
        # Second window
        assert await limiter.acquire(blocking=False) is True
        assert await limiter.acquire(blocking=False) is True
        assert await limiter.acquire(blocking=False) is False

    @pytest.mark.asyncio
    async def test_non_blocking_event_loop(self):
        """Test that rate limiter doesn't block event loop."""
        limiter = AsyncRateLimiter(max_calls=1, time_window_seconds=1)
        
        # First call
        await limiter.acquire(blocking=True)
        
        # Start a task that should run concurrently
        task_completed = False
        
        async def concurrent_task():
            nonlocal task_completed
            await asyncio.sleep(0.1)
            task_completed = True
        
        # Start concurrent task and rate-limited call
        start_time = time.time()
        await asyncio.gather(
            limiter.acquire(blocking=True),
            concurrent_task()
        )
        elapsed = time.time() - start_time
        
        # Concurrent task should complete quickly
        assert task_completed is True
        # Total time should be approximately 1 second (rate limit wait)
        assert 0.9 <= elapsed <= 1.5

