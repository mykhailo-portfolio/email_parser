"""
Module entry point for running Email Parser as a Python module.

Usage:
    python -m app                    # Run pipeline once (sync)
    python -m app --async            # Run pipeline once (async)
    python -m app service            # Run service with scheduler (sync)
    python -m app service --async    # Run service with scheduler (async)
    python -m app test               # Run test pipeline
"""

from __future__ import annotations
import sys
from cli import main

if __name__ == "__main__":
    main()

