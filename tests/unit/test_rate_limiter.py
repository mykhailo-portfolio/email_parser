"""
Unit tests for RateLimiter.
"""

import pytest
import time
import threading
from app.utils.rate_limiter import RateLimiter


class TestRateLimiter:
    """Test cases for RateLimiter."""

    def test_basic_acquire(self):
        """Test basic acquire functionality."""
        limiter = RateLimiter(max_calls=5, time_window_seconds=60)
        
        # Should allow 5 calls
        for i in range(5):
            assert limiter.acquire(blocking=False) is True
        
        # 6th call should be blocked
        assert limiter.acquire(blocking=False) is False

    def test_time_window(self):
        """Test that time window works correctly."""
        limiter = RateLimiter(max_calls=2, time_window_seconds=1)
        
        # Make 2 calls
        assert limiter.acquire(blocking=False) is True
        assert limiter.acquire(blocking=False) is True
        
        # 3rd call should be blocked
        assert limiter.acquire(blocking=False) is False
        
        # Wait for time window to expire
        time.sleep(1.1)
        
        # Should allow calls again
        assert limiter.acquire(blocking=False) is True

    def test_blocking_mode(self):
        """Test blocking mode."""
        limiter = RateLimiter(max_calls=1, time_window_seconds=1)
        
        # First call should succeed
        assert limiter.acquire(blocking=True) is True
        
        # Second call should block and wait
        start_time = time.time()
        assert limiter.acquire(blocking=True) is True
        elapsed = time.time() - start_time
        
        # Should have waited approximately 1 second
        assert 0.9 <= elapsed <= 1.5  # Allow some tolerance

    def test_timeout(self):
        """Test timeout handling."""
        limiter = RateLimiter(max_calls=1, time_window_seconds=2)
        
        # First call should succeed
        assert limiter.acquire(blocking=True) is True
        
        # Second call with short timeout should fail
        start_time = time.time()
        result = limiter.acquire(blocking=True, timeout=0.5)
        elapsed = time.time() - start_time
        
        assert result is False
        assert elapsed < 1.0  # Should return quickly due to timeout

    def test_thread_safety(self):
        """Test thread safety with concurrent access."""
        limiter = RateLimiter(max_calls=10, time_window_seconds=60)
        results = []
        errors = []
        
        def worker():
            try:
                for _ in range(5):
                    result = limiter.acquire(blocking=False)
                    results.append(result)
            except Exception as e:
                errors.append(e)
        
        # Create multiple threads
        threads = []
        for _ in range(5):
            t = threading.Thread(target=worker)
            threads.append(t)
            t.start()
        
        # Wait for all threads to complete
        for t in threads:
            t.join()
        
        # Should have no errors
        assert len(errors) == 0
        
        # Should have exactly 10 True results (max_calls)
        assert results.count(True) == 10
        
        # Remaining should be False
        assert results.count(False) == 15  # 5 threads * 5 calls - 10 allowed = 15

    def test_context_manager(self):
        """Test context manager usage."""
        limiter = RateLimiter(max_calls=1, time_window_seconds=60)
        
        with limiter:
            # Should have acquired
            assert limiter.acquire(blocking=False) is False
        
        # After context exit, should be able to acquire again
        # (context manager doesn't release, but we can test the pattern)
        limiter2 = RateLimiter(max_calls=2, time_window_seconds=60)
        with limiter2:
            pass
        # Should still have 1 slot available
        assert limiter2.acquire(blocking=False) is True

    def test_multiple_windows(self):
        """Test behavior across multiple time windows."""
        limiter = RateLimiter(max_calls=2, time_window_seconds=1)
        
        # First window
        assert limiter.acquire(blocking=False) is True
        assert limiter.acquire(blocking=False) is True
        assert limiter.acquire(blocking=False) is False
        
        # Wait for window to expire
        time.sleep(1.1)
        
        # Second window
        assert limiter.acquire(blocking=False) is True
        assert limiter.acquire(blocking=False) is True
        assert limiter.acquire(blocking=False) is False

