"""
Basic usage example for Email Parser.

This example demonstrates how to use the Email Parser programmatically
to process emails and update Google Sheets.
"""

from app.config import _load_env, _init_clients
from app.utils.filters import filter_by_company, classify_latest
from app.sheets.writer import update_sheet_statuses, update_sheet_review
from app.logging import logger, setup_logging


def main():
    """Example: Process emails and update Google Sheets."""
    # Load configuration from environment
    cfg = _load_env()
    
    # Setup logging
    setup_logging(
        log_level=cfg["LOG_LEVEL"],
        log_file=cfg["LOG_FILE"],
    )
    
    logger.info("Starting email processing example")
    
    try:
        # Initialize clients (Gmail, Sheets, Storage)
        sheets, gmail, storage = _init_clients(cfg)
        logger.info("Clients initialized successfully")
        
        # Step 1: Fetch companies from Google Sheets
        companies_data = sheets.fetch_pending_companies(
            spreadsheet_id=cfg["SHEET_ID"],
            sheet_name=cfg["SHEET_TAB"],
            start_row=cfg["START_ROW"],
        )
        companies = [name for _, name in companies_data]
        logger.info(f"Found {len(companies)} companies to process")
        
        if not companies:
            logger.info("No companies to process")
            return
        
        # Step 2: Collect new Gmail messages
        message_ids, last_id, has_more = gmail.collect_new_messages_once(
            storage=storage,
            pointer_key=cfg["POINTER_KEY"],
            limit=cfg["BATCH_LIMIT"],
            query=cfg["GMAIL_QUERY"],
        )
        logger.info(f"Found {len(message_ids)} new messages")
        
        if not message_ids:
            logger.info("No new messages to process")
            return
        
        # Step 3: Get email briefs (full body + head)
        briefs = gmail.get_message_briefs(message_ids)
        logger.info(f"Retrieved {len(briefs)} email briefs")
        
        # Step 4: Filter emails by company
        filtered = filter_by_company(briefs, companies)
        matched_count = sum(len(emails) for emails in filtered.values())
        logger.info(f"Matched {matched_count} emails to {len(filtered)} companies")
        
        if not filtered:
            logger.info("No company-related emails found")
            # Still advance pointer
            gmail.advance_pointer_after_processing(
                storage, last_id, pointer_key=cfg["POINTER_KEY"]
            )
            return
        
        # Step 5: Classify emails
        classified = classify_latest(filtered)
        
        approve_count = sum(len(v) for v in classified.get("approve", {}).values())
        decline_count = sum(len(v) for v in classified.get("decline", {}).values())
        review_count = sum(len(v) for v in classified.get("review", {}).values())
        
        logger.info(
            f"Classification results: {approve_count} approved, "
            f"{decline_count} declined, {review_count} needs review"
        )
        
        # Step 6: Update Google Sheets
        if approve_count or decline_count:
            update_sheet_statuses(
                sheets=sheets,
                sheet_id=cfg["SHEET_ID"],
                sheet_tab=cfg["SHEET_TAB"],
                results=classified,
            )
            logger.info("Updated sheet statuses (column C)")
        
        if review_count:
            update_sheet_review(
                sheets=sheets,
                sheet_id=cfg["SHEET_ID"],
                sheet_tab=cfg["SHEET_TAB"],
                results=classified,
            )
            logger.info("Updated review flags (column B)")
        
        # Step 7: Advance pointer
        gmail.advance_pointer_after_processing(
            storage, last_id, pointer_key=cfg["POINTER_KEY"]
        )
        logger.info("Pointer advanced successfully")
        
        logger.info("Email processing completed successfully")
        
    except Exception as e:
        logger.exception(f"Error processing emails: {e}")
        raise


if __name__ == "__main__":
    main()

