"""
Logging configuration using loguru.

Provides structured logging with file rotation and console output.
"""

from __future__ import annotations
from pathlib import Path
from loguru import logger


def setup_logging(
    log_level: str = "INFO",
    log_file: str | Path | None = None,
    rotation: str = "10 MB",
    retention: str = "7 days",
    console_level: str | None = None,
) -> None:
    """
    Configure loguru logger with console and optional file output.

    Args:
        log_level: Logging level for file (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to log file. If None, only console logging.
        rotation: Log rotation size (e.g., "10 MB", "1 GB")
        retention: Log retention period (e.g., "7 days", "1 month")
        console_level: Logging level for console. If None, uses WARNING when log_file is set, otherwise uses log_level.
    """
    # Remove default handler
    logger.remove()

    # Determine console log level
    # If log file is specified, console shows only warnings and errors by default
    # Otherwise, console uses the same level as file
    if console_level is None:
        console_level = "WARNING" if log_file else log_level

    # Console handler with color (only warnings and errors if file logging is enabled)
    import sys
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=console_level,
        colorize=True,
    )

    # File handler (if specified) - logs everything at specified level
    if log_file:
        log_path = Path(log_file)
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            # Test write access
            test_file = log_path.parent / ".log_test"
            test_file.touch()
            test_file.unlink()
            
            logger.add(
                log_path,
                format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
                level=log_level,
                rotation=rotation,
                retention=retention,
                compression="zip",
                encoding="utf-8",
                catch=True,  # Catch exceptions in logging handler
            )
            # Log to console that file logging is enabled
            import sys
            print(f"Logging to file: {log_path}", file=sys.stderr)
        except Exception as e:
            # If file logging fails, log to console and continue
            import sys
            print(f"WARNING: Failed to setup file logging to {log_path}: {e}", file=sys.stderr)
            print("Continuing with console logging only", file=sys.stderr)


# Export logger instance for use throughout the application
__all__ = ["logger", "setup_logging"]

