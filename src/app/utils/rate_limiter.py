"""
Rate limiter for API calls to prevent exceeding quotas.
"""

from __future__ import annotations
import time
import threading
import asyncio
from collections import deque
from typing import Optional
from app.logging import logger


class RateLimiter:
    """
    Simple token bucket rate limiter.
    
    Tracks API calls within a time window and blocks if limit is exceeded.
    Thread-safe implementation using locks.
    """

    def __init__(self, max_calls: int, time_window_seconds: int = 60):
        """
        Initialize rate limiter.

        Args:
            max_calls: Maximum number of calls allowed in the time window
            time_window_seconds: Time window in seconds (default: 60 = 1 minute)
        """
        self.max_calls = max_calls
        self.time_window = time_window_seconds
        self.call_times: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self, blocking: bool = True, timeout: Optional[float] = None) -> bool:
        """
        Acquire permission to make an API call.

        Args:
            blocking: If True, wait until a call slot is available
            timeout: Maximum time to wait in seconds (None = wait indefinitely)

        Returns:
            True if permission granted, False if timeout exceeded
        """
        now = time.time()
        
        with self._lock:
            # Remove calls outside the time window
            while self.call_times and (now - self.call_times[0]) > self.time_window:
                self.call_times.popleft()

            # Check if we can make a call
            if len(self.call_times) < self.max_calls:
                self.call_times.append(now)
                return True

            # Rate limit exceeded
            if not blocking:
                logger.warning(
                    f"Rate limit exceeded: {len(self.call_times)}/{self.max_calls} calls "
                    f"in the last {self.time_window}s"
                )
                return False

            # Calculate wait time (need to keep lock to read oldest_call)
            oldest_call = self.call_times[0]
            wait_time = self.time_window - (now - oldest_call) + 0.1  # Add small buffer

        # Release lock before sleeping to avoid blocking other threads
        if timeout is not None and wait_time > timeout:
            logger.warning(f"Rate limit wait time ({wait_time:.2f}s) exceeds timeout ({timeout}s)")
            return False

        logger.debug(f"Rate limit reached, waiting {wait_time:.2f}s...")
        time.sleep(wait_time)

        # Retry after waiting (will acquire lock again)
        return self.acquire(blocking=False)

    def __enter__(self):
        """Context manager entry."""
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        pass


class AsyncRateLimiter:
    """
    Async token bucket rate limiter.
    
    Tracks API calls within a time window and blocks if limit is exceeded.
    Async-safe implementation using asyncio locks.
    """

    def __init__(self, max_calls: int, time_window_seconds: int = 60):
        """
        Initialize async rate limiter.

        Args:
            max_calls: Maximum number of calls allowed in the time window
            time_window_seconds: Time window in seconds (default: 60 = 1 minute)
        """
        self.max_calls = max_calls
        self.time_window = time_window_seconds
        self.call_times: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self, blocking: bool = True, timeout: Optional[float] = None) -> bool:
        """
        Acquire permission to make an API call (async).

        Args:
            blocking: If True, wait until a call slot is available
            timeout: Maximum time to wait in seconds (None = wait indefinitely)

        Returns:
            True if permission granted, False if timeout exceeded
        """
        now = time.time()
        
        async with self._lock:
            # Remove calls outside the time window
            while self.call_times and (now - self.call_times[0]) > self.time_window:
                self.call_times.popleft()

            # Check if we can make a call
            if len(self.call_times) < self.max_calls:
                self.call_times.append(now)
                return True

            # Rate limit exceeded
            if not blocking:
                logger.warning(
                    f"Rate limit exceeded: {len(self.call_times)}/{self.max_calls} calls "
                    f"in the last {self.time_window}s"
                )
                return False

            # Calculate wait time (need to keep lock to read oldest_call)
            oldest_call = self.call_times[0]
            wait_time = self.time_window - (now - oldest_call) + 0.1  # Add small buffer

        # Release lock before sleeping to avoid blocking other coroutines
        if timeout is not None and wait_time > timeout:
            logger.warning(f"Rate limit wait time ({wait_time:.2f}s) exceeds timeout ({timeout}s)")
            return False

        logger.debug(f"Rate limit reached, waiting {wait_time:.2f}s...")
        await asyncio.sleep(wait_time)

        # Retry after waiting (will acquire lock again)
        return await self.acquire(blocking=False)

    async def __aenter__(self):
        """Async context manager entry."""
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        pass

