"""
Command-line interface for Email Parser.
"""

from __future__ import annotations
import sys
import argparse
from pathlib import Path

# Add src to path for imports
PROJ_ROOT = Path(__file__).resolve().parent
if str(PROJ_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJ_ROOT))

from app.config import _load_env
from app.logging import logger, setup_logging
from app.pipeline.run import main as run_pipeline
from app.pipeline.run_async import main_async
from app.service import main as run_service
from app.service_async import main as run_service_async
import asyncio


def cmd_run(args):
    """Run pipeline once (synchronous)."""
    try:
        cfg = _load_env()
        setup_logging(
            log_level=cfg["LOG_LEVEL"],
            log_file=cfg["LOG_FILE"],
        )
        logger.info("Running pipeline (sync mode)")
        run_pipeline()
    except Exception as e:
        logger.exception(f"Pipeline execution failed: {e}")
        sys.exit(1)


def cmd_run_async(args):
    """Run pipeline once (asynchronous)."""
    try:
        cfg = _load_env()
        setup_logging(
            log_level=cfg["LOG_LEVEL"],
            log_file=cfg["LOG_FILE"],
        )
        logger.info("Running pipeline (async mode)")
        asyncio.run(main_async())
    except Exception as e:
        logger.exception(f"Async pipeline execution failed: {e}")
        sys.exit(1)


def cmd_service(args):
    """Run service with scheduler (synchronous)."""
    try:
        run_service()
    except Exception as e:
        logger.exception(f"Service execution failed: {e}")
        sys.exit(1)


def cmd_service_async(args):
    """Run service with scheduler (asynchronous)."""
    try:
        run_service_async()
    except Exception as e:
        logger.exception(f"Async service execution failed: {e}")
        sys.exit(1)


def cmd_test(args):
    """Run test pipeline."""
    try:
        from test_pipeline import main as run_test
        run_test()
    except Exception as e:
        logger.exception(f"Test execution failed: {e}")
        sys.exit(1)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Email Parser - Automated email classification for job applications",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s run              Run pipeline once (sync)
  %(prog)s run --async      Run pipeline once (async)
  %(prog)s service          Run service with scheduler (sync)
  %(prog)s service --async  Run service with scheduler (async)
  %(prog)s test             Run test pipeline
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Run command
    run_parser = subparsers.add_parser("run", help="Run pipeline once")
    run_parser.add_argument(
        "--async",
        action="store_true",
        dest="use_async",
        help="Use async pipeline"
    )
    run_parser.set_defaults(func=cmd_run)
    
    # Service command
    service_parser = subparsers.add_parser("service", help="Run service with scheduler")
    service_parser.add_argument(
        "--async",
        action="store_true",
        dest="use_async",
        help="Use async service"
    )
    service_parser.set_defaults(func=cmd_service)
    
    # Test command
    test_parser = subparsers.add_parser("test", help="Run test pipeline")
    test_parser.set_defaults(func=cmd_test)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Handle async flag for run and service commands
    if args.command == "run" and hasattr(args, "use_async") and args.use_async:
        args.func = cmd_run_async
    elif args.command == "service" and hasattr(args, "use_async") and args.use_async:
        args.func = cmd_service_async
    
    args.func(args)


if __name__ == "__main__":
    main()

