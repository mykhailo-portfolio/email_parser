"""
Scheduler for periodic pipeline execution with graceful shutdown support.
Supports both sync and async pipeline functions.
"""

from __future__ import annotations
import signal
import sys
import time
import threading
import asyncio
from typing import Optional, Callable, Union, Coroutine
from app.logging import logger


class PipelineScheduler:
    """
    Scheduler for running pipeline periodically with graceful shutdown support.
    
    Supports:
    - Periodic execution with configurable interval
    - Both sync and async pipeline functions
    - Graceful shutdown on SIGTERM/SIGINT
    - Health check endpoint (optional)
    - Statistics tracking
    """
    
    def __init__(
        self,
        pipeline_func: Union[Callable[[], None], Callable[[], Coroutine]],
        interval_seconds: int = 300,  # 5 minutes default
    ) -> None:
        """
        Initialize scheduler.
        
        Args:
            pipeline_func: Function to execute on each run (sync or async)
            interval_seconds: Interval between runs in seconds
        """
        self.pipeline_func = pipeline_func
        self.interval_seconds = interval_seconds
        self.running = False
        self.shutdown_requested = False
        self.thread: Optional[threading.Thread] = None
        self.stats = {
            "runs": 0,
            "successful_runs": 0,
            "failed_runs": 0,
            "last_run_time": None,
            "last_success_time": None,
            "last_error": None,
        }
        # Detect if pipeline function is async
        self.is_async = asyncio.iscoroutinefunction(pipeline_func)
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, signum: int, frame) -> None:
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.shutdown_requested = True
        self.stop()
    
    def _run_pipeline(self) -> None:
        """Execute pipeline function with error handling (supports both sync and async)."""
        try:
            start_time = time.time()
            
            if self.is_async:
                # Run async function in new event loop
                asyncio.run(self.pipeline_func())
            else:
                # Run sync function directly
                self.pipeline_func()
            
            duration = time.time() - start_time
            self.stats["runs"] += 1
            self.stats["successful_runs"] += 1
            self.stats["last_run_time"] = time.time()
            self.stats["last_success_time"] = time.time()
            self.stats["last_error"] = None
            
            # Only log successful runs if they took too long (potential issue) or if explicitly needed
            # Regular successful runs without changes are logged by pipeline itself if needed
            
        except Exception as e:
            duration = time.time() - start_time if 'start_time' in locals() else 0
            self.stats["runs"] += 1
            self.stats["failed_runs"] += 1
            self.stats["last_run_time"] = time.time()
            self.stats["last_error"] = str(e)
            
            logger.exception(f"Pipeline run failed after {duration:.2f}s: {e}")
    
    def _scheduler_loop(self) -> None:
        """Main scheduler loop."""
        logger.info(f"Scheduler started with interval {self.interval_seconds}s")
        
        while self.running and not self.shutdown_requested:
            # Run pipeline
            self._run_pipeline()
            
            # Wait for next run (with periodic checks for shutdown)
            if not self.shutdown_requested:
                wait_interval = 1.0  # Check every second
                waited = 0
                while waited < self.interval_seconds and not self.shutdown_requested:
                    time.sleep(min(wait_interval, self.interval_seconds - waited))
                    waited += wait_interval
        
        logger.info("Scheduler loop ended")
    
    def start(self) -> None:
        """Start the scheduler in a background thread."""
        if self.running:
            logger.warning("Scheduler is already running")
            return
        
        self.running = True
        self.shutdown_requested = False
        self.thread = threading.Thread(target=self._scheduler_loop, daemon=False)
        self.thread.start()
        logger.info("Scheduler started")
    
    def stop(self, timeout: float = 30.0) -> None:
        """
        Stop the scheduler gracefully.
        
        Args:
            timeout: Maximum time to wait for current run to complete
        """
        if not self.running:
            return
        
        logger.info("Stopping scheduler...")
        self.running = False
        self.shutdown_requested = True
        
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=timeout)
            if self.thread.is_alive():
                logger.warning(f"Scheduler thread did not stop within {timeout}s")
            else:
                logger.info("Scheduler stopped gracefully")
    
    def get_health(self) -> dict:
        """
        Get health check information.
        
        Returns:
            Dictionary with health status and statistics
        """
        is_healthy = (
            self.running and
            self.stats["runs"] > 0 and
            self.stats["last_error"] is None
        )
        
        # Consider unhealthy if last run was more than 2 intervals ago
        if self.stats["last_run_time"]:
            time_since_last_run = time.time() - self.stats["last_run_time"]
            if time_since_last_run > (self.interval_seconds * 2):
                is_healthy = False
        
        return {
            "status": "healthy" if is_healthy else "unhealthy",
            "running": self.running,
            "shutdown_requested": self.shutdown_requested,
            "stats": self.stats.copy(),
            "interval_seconds": self.interval_seconds,
        }
    
    def wait(self) -> None:
        """Wait for scheduler thread to complete."""
        if self.thread:
            self.thread.join()

