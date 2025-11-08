"""
Async end-to-end pipeline:
- Read pending companies from Google Sheets
- Fetch new Gmail messages since pointer (in parallel)
- Build message briefs (full body + recent head)
- Stage-1: keep emails that mention a known company (by head)
- Stage-2: classify by first-hit (approve / decline / review)
- Advance pointer
"""

from __future__ import annotations
import sys
import asyncio
from pathlib import Path

# ---- ensure src/ is importable when running the file directly
PROJ_ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = PROJ_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# ---- project imports
from app.config import _load_env, Config, _init_storage, _load_and_refresh_credentials
from app.utils.filters import filter_by_company, classify_latest
from app.logging import logger, setup_logging
from app.auth import TokenExpiredError
from app.gmail.client_async import AsyncGmailClient
from app.sheets.client_async import AsyncSheetsClient
from app.storage.local_state import PointerStorage
import gspread
from googleapiclient.discovery import build


async def _init_async_clients(cfg: Config) -> tuple[AsyncSheetsClient, AsyncGmailClient, PointerStorage]:
    """
    Initialize async Google clients and pointer storage.

    Args:
        cfg: Configuration dictionary

    Returns:
        Tuple of (AsyncSheetsClient, AsyncGmailClient, PointerStorage)

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
        sheets = AsyncSheetsClient(gspread_client)

        gmail_service = build("gmail", "v1", credentials=gmail_creds)
        
        # Initialize async rate limiter for Gmail API
        from app.utils.rate_limiter import AsyncRateLimiter
        rate_limiter = AsyncRateLimiter(
            max_calls=cfg["GMAIL_RATE_LIMIT_PER_MINUTE"],
            time_window_seconds=60
        )
        
        gmail = AsyncGmailClient(
            gmail_service,
            max_batch_size=cfg["GMAIL_MAX_BATCH_SIZE"],
            head_max_chars=cfg["GMAIL_HEAD_MAX_CHARS"],
            rate_limiter=rate_limiter,
        )

        # Initialize storage with fallback
        storage = _init_storage(cfg)

        logger.info("Async clients initialized successfully")
        return sheets, gmail, storage

    except Exception as e:
        logger.error(f"Failed to initialize async clients: {e}")
        raise


async def main_async() -> None:
    """Main async pipeline execution function."""
    try:
        # Setup logging first
        cfg = _load_env()
        setup_logging(
            log_level=cfg["LOG_LEVEL"],
            log_file=cfg["LOG_FILE"],
        )

        logger.info("Starting async email parser pipeline")
        try:
            sheets, gmail, storage = await _init_async_clients(cfg)
        except TokenExpiredError:
            logger.error("Pipeline stopped due to token expiration")
            return

        # ---- 1) Companies from Google Sheets
        try:
            rows = await sheets.fetch_pending_companies(
                spreadsheet_id=cfg["SHEET_ID"],
                sheet_name=cfg["SHEET_TAB"],
                start_row=cfg["START_ROW"],
            )
            companies = [name for _, name in rows]
            logger.info(f"Loaded {len(companies)} pending companies from Sheets")
        except Exception as e:
            logger.error(f"Failed to fetch companies from Sheets: {e}")
            raise

        # ---- 2) New Gmail message ids since pointer
        try:
            ids, head_id, has_more = await gmail.collect_new_messages_once(
                storage=storage,
                pointer_key=cfg["POINTER_KEY"],
                limit=cfg["BATCH_LIMIT"],
                query=cfg["GMAIL_QUERY"],
            )
            logger.info(f"Found {len(ids)} new message IDs (has_more={has_more})")
        except Exception as e:
            logger.error(f"Failed to collect new messages: {e}")
            raise

        if not ids:
            logger.info("No new messages to process")
            return

        # ---- 3) Message briefs (include body 'head' for classification) - PARALLEL PROCESSING
        try:
            briefs = await gmail.get_message_briefs(ids, max_concurrent=10)
            logger.info(f"Retrieved {len(briefs)} message briefs")
        except Exception as e:
            logger.error(f"Failed to get message briefs: {e}")
            raise

        if not briefs or not companies:
            gmail.advance_pointer_after_processing(storage, head_id, pointer_key=cfg["POINTER_KEY"])
            logger.info("Nothing to process (no briefs or no companies)")
            return

        # ---- 4) Stage-1: company relevance (by head only)
        related = filter_by_company(briefs, companies)
        matched_msgs = sum(len(v) for v in related.values())
        logger.info(f"Stage-1: matched {len(related)} companies with {matched_msgs} messages")

        if not related:
            gmail.advance_pointer_after_processing(storage, head_id, pointer_key=cfg["POINTER_KEY"])
            logger.info("No company-related emails found")
            return

        # ---- 5) Stage-2: latest + first-hit classification (approve / decline / review)
        classified = classify_latest(related)

        def _count(bucket: str) -> int:
            return sum(len(v) for v in classified.get(bucket, {}).values())

        count_approve = _count("approve")
        count_decline = _count("decline")
        count_review = _count("review")

        logger.info(f"Stage-2: approve={count_approve}, decline={count_decline}, review={count_review}")

        # ---- 6) Update Google Sheets (async)
        if count_approve or count_decline:
            from app.sheets.writer_async import update_sheet_statuses
            try:
                await update_sheet_statuses(
                    sheets=sheets,
                    sheet_id=cfg["SHEET_ID"],
                    sheet_tab=cfg["SHEET_TAB"],
                    results=classified,
                )
                logger.info("Sheet statuses updated successfully (column C)")
            except Exception as e:
                logger.error(f"Failed to update sheet statuses: {e}")
                raise
        else:
            logger.debug("No status updates needed (column C)")

        if count_review:
            from app.sheets.writer_async import update_sheet_review
            try:
                await update_sheet_review(
                    sheets=sheets,
                    sheet_id=cfg["SHEET_ID"],
                    sheet_tab=cfg["SHEET_TAB"],
                    results=classified,
                )
                logger.info("Sheet review flags updated successfully (column B)")
            except Exception as e:
                logger.error(f"Failed to update sheet review flags: {e}")
                raise
        else:
            logger.debug("No review flags to update")

        # Advance pointer after successful processing
        gmail.advance_pointer_after_processing(storage, head_id, pointer_key=cfg["POINTER_KEY"])

        logger.info("Async pipeline execution completed successfully")

    except Exception as e:
        logger.exception(f"Async pipeline execution failed: {e}")
        raise


def main() -> None:
    """Synchronous entry point that runs the async pipeline."""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()

