# src/app/pipeline/run.py
"""
End-to-end pipeline:
- Read pending companies from Google Sheets
- Fetch new Gmail messages since pointer
- Build message briefs (full body + recent head)
- Stage-1: keep emails that mention a known company (by head)
- Stage-2: classify by first-hit (approve / decline / review)
- Advance pointer
"""

from __future__ import annotations
import sys
from pathlib import Path

# ---- ensure src/ is importable when running the file directly
PROJ_ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = PROJ_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# ---- project imports
from app.config import _load_env, _init_clients, Config
from app.utils.filters import filter_by_company, classify_latest
from app.logging import logger, setup_logging
from app.auth import TokenExpiredError



def main() -> None:
    """Main pipeline execution function."""
    try:
        # Setup logging first
        cfg = _load_env()
        setup_logging(
            log_level=cfg["LOG_LEVEL"],
            log_file=cfg["LOG_FILE"],
        )

        logger.info("Starting email parser pipeline")
        try:
            sheets, gmail, storage = _init_clients(cfg)
        except TokenExpiredError:
            # Error already logged in _init_clients with instructions
            logger.error("Pipeline stopped due to token expiration")
            return

        # ---- 1) Companies from Google Sheets
        try:
            rows = sheets.fetch_pending_companies(
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
            ids, head_id, has_more = gmail.collect_new_messages_once(
                storage=storage,
                pointer_key=cfg["POINTER_KEY"],
                limit=cfg["BATCH_LIMIT"],
                query=cfg["GMAIL_QUERY"],
            )
        except Exception as e:
            logger.error(f"Failed to collect new messages: {e}")
            raise

        if not ids:
            logger.info("No new messages to process")
            return

        # ---- 3) Message briefs (include body 'head' for classification)
        try:
            briefs = gmail.get_message_briefs(ids)
        except Exception as e:
            logger.error(f"Failed to get message briefs: {e}")
            raise

        if not briefs or not companies:
            gmail.advance_pointer_after_processing(storage, head_id, pointer_key=cfg["POINTER_KEY"])
            logger.warning("No briefs retrieved or no companies to process")
            return

        # ---- 4) Stage-1: company relevance (by head only)
        related = filter_by_company(briefs, companies)
        matched_msgs = sum(len(v) for v in related.values())

        if not related:
            gmail.advance_pointer_after_processing(storage, head_id, pointer_key=cfg["POINTER_KEY"])
            return  # No company matches - skip logging

        # ---- 5) Stage-2: latest + first-hit classification (approve / decline / review)
        classified = classify_latest(related)

        def _count(bucket: str) -> int:
            return sum(len(v) for v in classified.get(bucket, {}).values())

        count_approve = _count("approve")
        count_decline = _count("decline")
        count_review  = _count("review")

        # Only log if there are actual changes
        if not (count_approve or count_decline or count_review):
            gmail.advance_pointer_after_processing(storage, head_id, pointer_key=cfg["POINTER_KEY"])
            return  # No changes - skip logging

        # Log pipeline execution with changes
        logger.info(f"Processing {matched_msgs} messages for {len(related)} companies")
        logger.info(f"Classification: approve={count_approve}, decline={count_decline}, review={count_review}")

        # ---- 6) Update Google Sheets
        if count_approve or count_decline:
            from app.sheets.writer import update_sheet_statuses
            try:
                update_sheet_statuses(
                    sheets=sheets,
                    sheet_id=cfg["SHEET_ID"],
                    sheet_tab=cfg["SHEET_TAB"],
                    results=classified,
                )
                logger.info(f"Updated {count_approve + count_decline} statuses in column C")
            except Exception as e:
                logger.error(f"Failed to update sheet statuses: {e}")
                raise

        if count_review:
            from app.sheets.writer import update_sheet_review
            try:
                update_sheet_review(
                    sheets=sheets,
                    sheet_id=cfg["SHEET_ID"],
                    sheet_tab=cfg["SHEET_TAB"],
                    results=classified,
                )
                logger.info(f"Updated {count_review} review flags in column B")
            except Exception as e:
                logger.error(f"Failed to update sheet review flags: {e}")
                raise

        # Advance pointer after successful processing
        gmail.advance_pointer_after_processing(storage, head_id, pointer_key=cfg["POINTER_KEY"])

    except Exception as e:
        logger.exception(f"Pipeline execution failed: {e}")
        raise

if __name__ == "__main__":
    main()
