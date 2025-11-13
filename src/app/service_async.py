"""
Async main service entry point with scheduler and health check support.
"""

from __future__ import annotations
import sys
import asyncio
from pathlib import Path

# ---- ensure src/ is importable when running the file directly
PROJ_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJ_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from app.config import _load_env
from app.logging import logger, setup_logging
from app.auth import TokenExpiredError
from app.scheduler import PipelineScheduler
from app.health import HealthCheckServer
from app.pipeline.run_async import main_async


def main() -> None:
    """Main async service entry point."""
    health_server = None
    scheduler = None
    
    try:
        # Setup basic logging first (before loading full config to avoid logs before setup)
        import os
        from dotenv import load_dotenv
        load_dotenv()
        log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
        log_file = os.getenv("LOG_FILE", "").strip() or None
        
        setup_logging(
            log_level=log_level,
            log_file=log_file,
        )
        
        # Now load full configuration (this may log, but logging is already set up)
        cfg = _load_env()
        
        logger.info("Starting async email parser service")
        
        # Initialize health check server if enabled
        if cfg["HEALTH_CHECK_ENABLED"]:
            try:
                def initial_health_func(*args, **kwargs):
                    """Health check function that accepts any arguments for compatibility."""
                    return {"status": "initializing", "scheduler": "not_started"}
                
                health_server = HealthCheckServer(
                    port=cfg["HEALTH_CHECK_PORT"],
                    health_func=initial_health_func,
                )
                health_server.start()
                logger.info(f"Health check server started on port {cfg['HEALTH_CHECK_PORT']}")
            except Exception as e:
                logger.warning(f"Failed to start health check server: {e}")
        
        # Initialize scheduler if enabled
        if cfg["SCHEDULER_ENABLED"]:
            try:
                # Use async pipeline function
                scheduler = PipelineScheduler(
                    pipeline_func=main_async,
                    interval_seconds=cfg["SCHEDULER_INTERVAL"],
                )
                
                # Update health_func to use scheduler's health
                if health_server:
                    health_server._health_func = scheduler.get_health
                
                scheduler.start()
                logger.info(f"Async scheduler started with interval {cfg['SCHEDULER_INTERVAL']}s")
                
                try:
                    scheduler.wait()
                except KeyboardInterrupt:
                    logger.info("Received interrupt signal")
                    scheduler.stop()
            except TokenExpiredError:
                logger.error("Cannot start scheduler - token expired")
                raise
        else:
            logger.info("Scheduler disabled, running async pipeline once")
            asyncio.run(main_async())
        
    except KeyboardInterrupt:
        logger.info("Service interrupted by user")
    except Exception as e:
        logger.exception(f"Service failed: {e}")
        raise
    finally:
        if scheduler:
            scheduler.stop()
        if health_server:
            health_server.stop()
        logger.info("Service stopped")


if __name__ == "__main__":
    main()

