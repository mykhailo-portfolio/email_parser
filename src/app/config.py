"""
Configuration management with validation and storage backend selection.
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import TypedDict
import gspread

from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.gmail.client import GmailClient
from app.sheets.client import SheetsClient
from app.storage.local_state import PointerStorage, InMemoryEmailStorage
from app.logging import logger
from app.auth import ensure_valid_credentials, TokenExpiredError
from google.auth.exceptions import RefreshError


class Config(TypedDict):
    """Typed configuration dictionary."""
    SHEETS_TOKEN: str
    GMAIL_TOKEN: str
    SHEET_ID: str
    SHEET_TAB: str
    START_ROW: int
    POINTER_KEY: str
    GMAIL_QUERY: str
    BATCH_LIMIT: int
    GMAIL_MAX_BATCH_SIZE: int  # Maximum messages to fetch per batch (default: 325)
    GMAIL_HEAD_MAX_CHARS: int  # Maximum characters in email head (default: 2000)
    GMAIL_RATE_LIMIT_PER_MINUTE: int  # Rate limit for Gmail API calls per minute (default: 100)
    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_DB: int
    USE_REDIS: bool
    LOG_LEVEL: str
    LOG_FILE: str | None
    AUTO_REAUTHORIZE: bool
    GMAIL_SCOPES: list[str]
    SHEETS_SCOPES: list[str]
    SCHEDULER_ENABLED: bool
    SCHEDULER_INTERVAL: int
    HEALTH_CHECK_ENABLED: bool
    HEALTH_CHECK_PORT: int


def _load_env() -> Config:
    """
    Load environment variables and return validated configuration.

    Required vars:
      - GOOGLE_SHEETS_TOKEN, GOOGLE_GMAIL_TOKEN (authorized user files)
      - GOOGLE_SHEET_ID

    Optional vars with defaults:
      - SHEET_WORKSHEET (default: "Applications")
      - START_ROW (default: 2)
      - GMAIL_POINTER_KEY (default: "gmail:last_processed_id")
      - GMAIL_QUERY (default: "-in:spam -in:trash")
      - GMAIL_BATCH_LIMIT (default: 200)
      - REDIS_HOST (default: "localhost")
      - REDIS_PORT (default: 6379)
      - REDIS_DB (default: 0)
      - USE_REDIS (default: "false")
      - LOG_LEVEL (default: "INFO")
      - LOG_FILE (default: None)
    """
    load_dotenv()

    # Required variables
    sheets_token = os.getenv("GOOGLE_SHEETS_TOKEN", "").strip()
    gmail_token = os.getenv("GOOGLE_GMAIL_TOKEN", "").strip()
    sheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip()

    # Validate required variables
    if not sheets_token:
        raise ValueError("GOOGLE_SHEETS_TOKEN environment variable is required")
    if not gmail_token:
        raise ValueError("GOOGLE_GMAIL_TOKEN environment variable is required")
    if not sheet_id:
        raise ValueError("GOOGLE_SHEET_ID environment variable is required")

    # Validate token files exist
    if not Path(sheets_token).exists():
        raise FileNotFoundError(f"GOOGLE_SHEETS_TOKEN file not found: {sheets_token}")
    if not Path(gmail_token).exists():
        raise FileNotFoundError(f"GOOGLE_GMAIL_TOKEN file not found: {gmail_token}")

    # Optional variables with defaults
    use_redis = os.getenv("USE_REDIS", "false").lower() in ("true", "1", "yes")
    redis_host = os.getenv("REDIS_HOST", "localhost").strip()
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    redis_db = int(os.getenv("REDIS_DB", "0"))

    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    log_file = os.getenv("LOG_FILE", "").strip() or None
    auto_reauthorize = os.getenv("AUTO_REAUTHORIZE", "false").lower() in ("true", "1", "yes")
    
    # Scheduler settings
    scheduler_enabled = os.getenv("SCHEDULER_ENABLED", "false").lower() in ("true", "1", "yes")
    scheduler_interval = int(os.getenv("SCHEDULER_INTERVAL", "300"))  # 5 minutes default
    
    # Health check settings
    health_check_enabled = os.getenv("HEALTH_CHECK_ENABLED", "true").lower() in ("true", "1", "yes")
    health_check_port = int(os.getenv("HEALTH_CHECK_PORT", "8080"))

    # OAuth scopes
    gmail_scopes_str = os.getenv(
        "GOOGLE_GMAIL_SCOPES",
        "https://www.googleapis.com/auth/gmail.readonly"
    )
    gmail_scopes = [s.strip() for s in gmail_scopes_str.split(",") if s.strip()]

    sheets_scopes_str = os.getenv(
        "GOOGLE_SHEETS_SCOPES",
        "https://www.googleapis.com/auth/spreadsheets,https://www.googleapis.com/auth/drive"
    )
    sheets_scopes = [s.strip() for s in sheets_scopes_str.split(",") if s.strip()]

    # Gmail API settings
    gmail_max_batch_size = int(os.getenv("GMAIL_MAX_BATCH_SIZE", "325"))
    gmail_head_max_chars = int(os.getenv("GMAIL_HEAD_MAX_CHARS", "2000"))
    gmail_rate_limit = int(os.getenv("GMAIL_RATE_LIMIT_PER_MINUTE", "100"))

    # Validate configuration values
    if scheduler_interval < 60:
        raise ValueError(
            f"SCHEDULER_INTERVAL must be at least 60 seconds, got {scheduler_interval}"
        )
    
    if not (1024 <= health_check_port <= 65535):
        raise ValueError(
            f"HEALTH_CHECK_PORT must be between 1024 and 65535, got {health_check_port}"
        )
    
    if not (1 <= redis_port <= 65535):
        raise ValueError(
            f"REDIS_PORT must be between 1 and 65535, got {redis_port}"
        )
    
    batch_limit = int(os.getenv("GMAIL_BATCH_LIMIT", "200"))
    if not (1 <= batch_limit <= 500):
        raise ValueError(
            f"GMAIL_BATCH_LIMIT must be between 1 and 500, got {batch_limit}"
        )
    
    if not (1 <= gmail_max_batch_size <= 500):
        raise ValueError(
            f"GMAIL_MAX_BATCH_SIZE must be between 1 and 500, got {gmail_max_batch_size}"
        )
    
    if not (1 <= gmail_rate_limit <= 1000):
        raise ValueError(
            f"GMAIL_RATE_LIMIT_PER_MINUTE must be between 1 and 1000, got {gmail_rate_limit}"
        )
    
    start_row = int(os.getenv("START_ROW", "2"))
    if start_row < 1:
        raise ValueError(
            f"START_ROW must be at least 1, got {start_row}"
        )

    cfg: Config = {
        "SHEETS_TOKEN": sheets_token,
        "GMAIL_TOKEN": gmail_token,
        "SHEET_ID": sheet_id,
        "SHEET_TAB": os.getenv("SHEET_WORKSHEET", "Applications").strip(),
        "START_ROW": start_row,
        "POINTER_KEY": os.getenv("GMAIL_POINTER_KEY", "gmail:last_processed_id"),
        "GMAIL_QUERY": os.getenv("GMAIL_QUERY", "-in:spam -in:trash"),
        "BATCH_LIMIT": batch_limit,
        "GMAIL_MAX_BATCH_SIZE": gmail_max_batch_size,
        "GMAIL_HEAD_MAX_CHARS": gmail_head_max_chars,
        "GMAIL_RATE_LIMIT_PER_MINUTE": gmail_rate_limit,
        "REDIS_HOST": redis_host,
        "REDIS_PORT": redis_port,
        "REDIS_DB": redis_db,
        "USE_REDIS": use_redis,
        "LOG_LEVEL": log_level,
        "LOG_FILE": log_file,
        "AUTO_REAUTHORIZE": auto_reauthorize,
        "GMAIL_SCOPES": gmail_scopes,
        "SHEETS_SCOPES": sheets_scopes,
        "SCHEDULER_ENABLED": scheduler_enabled,
        "SCHEDULER_INTERVAL": scheduler_interval,
        "HEALTH_CHECK_ENABLED": health_check_enabled,
        "HEALTH_CHECK_PORT": health_check_port,
    }

    logger.debug(f"Configuration loaded: USE_REDIS={use_redis}, LOG_LEVEL={log_level}")
    return cfg


def _init_clients(cfg: Config) -> tuple[SheetsClient, GmailClient, PointerStorage]:
    """
    Bootstrap Google clients and pointer storage with automatic fallback.

    Args:
        cfg: Configuration dictionary

    Returns:
        Tuple of (SheetsClient, GmailClient, PointerStorage)

    Raises:
        FileNotFoundError: If token files don't exist
        Exception: If credentials are invalid or expired
    """
    try:
        # Load and refresh credentials if needed
        sheets_creds = _load_and_refresh_credentials(
            token_path=cfg["SHEETS_TOKEN"],
            scopes=cfg["SHEETS_SCOPES"],
            auto_reauthorize=cfg["AUTO_REAUTHORIZE"],
        )
        gmail_creds = _load_and_refresh_credentials(
            token_path=cfg["GMAIL_TOKEN"],
            scopes=cfg["GMAIL_SCOPES"],
            auto_reauthorize=cfg["AUTO_REAUTHORIZE"],
        )

        gspread_client = gspread.authorize(sheets_creds)
        sheets = SheetsClient(gspread_client)

        gmail_service = build("gmail", "v1", credentials=gmail_creds)
        
        # Initialize rate limiter for Gmail API
        from app.utils.rate_limiter import RateLimiter
        rate_limiter = RateLimiter(
            max_calls=cfg["GMAIL_RATE_LIMIT_PER_MINUTE"],
            time_window_seconds=60
        )
        
        gmail = GmailClient(
            gmail_service,
            max_batch_size=cfg["GMAIL_MAX_BATCH_SIZE"],
            head_max_chars=cfg["GMAIL_HEAD_MAX_CHARS"],
            rate_limiter=rate_limiter,
        )

        # Initialize storage with fallback
        storage = _init_storage(cfg)

        logger.info("Clients initialized successfully")
        return sheets, gmail, storage

    except Exception as e:
        logger.error(f"Failed to initialize clients: {e}")
        raise


def _load_and_refresh_credentials(
    token_path: str,
    scopes: list[str],
    auto_reauthorize: bool = False,
) -> Credentials:
    """
    Load credentials from file and refresh if expired.
    Optionally re-authorize if refresh fails.

    Args:
        token_path: Path to token JSON file
        scopes: List of OAuth scopes required
        auto_reauthorize: If True, automatically start re-authorization flow on refresh failure.
                         If False, raises TokenExpiredError with instructions.

    Returns:
        Valid Credentials object

    Raises:
        FileNotFoundError: If token file doesn't exist
        TokenExpiredError: If refresh fails and auto_reauthorize is False
    """
    try:
        return ensure_valid_credentials(
            token_path=token_path,
            scopes=scopes,
            auto_reauthorize=auto_reauthorize,
        )
    except TokenExpiredError as e:
        logger.error(
            f"\n{'='*80}\n"
            f"❌ TOKEN EXPIRED - RE-AUTHORIZATION REQUIRED\n"
            f"{'='*80}\n"
            f"Error: {e}\n\n"
            f"To fix this, run:\n"
            f"  python scripts/bootstrap_oauth.py\n\n"
            f"Or set AUTO_REAUTHORIZE=true in .env to enable automatic re-authorization.\n"
            f"{'='*80}\n"
        )
        raise


def _init_storage(cfg: Config) -> PointerStorage:
    """
    Initialize storage backend with automatic fallback to InMemory.

    Args:
        cfg: Configuration dictionary

    Returns:
        PointerStorage instance (RedisKVStorage or InMemoryEmailStorage)
    """
    if cfg["USE_REDIS"]:
        try:
            from app.storage.redis_kv import RedisKVStorage
            storage = RedisKVStorage(
                host=cfg["REDIS_HOST"],
                port=cfg["REDIS_PORT"],
                db=cfg["REDIS_DB"],
            )
            logger.info(f"Using Redis storage at {cfg['REDIS_HOST']}:{cfg['REDIS_PORT']}")
            return storage
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}. Falling back to InMemory storage.")
            return InMemoryEmailStorage()
    else:
        logger.info("Using InMemory storage (Redis disabled)")
        return InMemoryEmailStorage()
