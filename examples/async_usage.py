"""
Asynchronous usage example for Email Parser.

This example demonstrates how to use the async Email Parser API
for better performance with large batches of emails.
"""

import asyncio
from app.config import _load_env
from app.pipeline.run_async import _init_async_clients
from app.utils.filters import filter_by_company, classify_latest
from app.sheets.writer_async import update_sheet_statuses, update_sheet_review
from app.logging import logger, setup_logging


async def main():
    """Example: Process emails asynchronously."""
    # Load configuration
    cfg = _load_env()
    
    # Setup logging
    setup_logging(
        log_level=cfg["LOG_LEVEL"],
        log_file=cfg["LOG_FILE"],
    )
    
    logger.info("Starting async email processing example")
    
    try:
        # Initialize async clients
        sheets, gmail, storage = await _init_async_clients(cfg)
        logger.info("Async clients initialized successfully")
        
        # Step 1: Fetch companies (async)
        companies_data = await sheets.fetch_pending_companies(
            spreadsheet_id=cfg["SHEET_ID"],
            sheet_name=cfg["SHEET_TAB"],
            start_row=cfg["START_ROW"],
        )
        companies = [name for _, name in companies_data]
        logger.info(f"Found {len(companies)} companies to process")
        
        if not companies:
            logger.info("No companies to process")
            return
        
        # Step 2: Collect new messages (async)
        message_ids, last_id, has_more = await gmail.collect_new_messages_once(
            storage=storage,
            pointer_key=cfg["POINTER_KEY"],
            limit=cfg["BATCH_LIMIT"],
            query=cfg["GMAIL_QUERY"],
        )
        logger.info(f"Found {len(message_ids)} new messages")
        
        if not message_ids:
            logger.info("No new messages to process")
            return
        
        # Step 3: Get email briefs (async, parallel processing)
        briefs = await gmail.get_message_briefs(message_ids)
        logger.info(f"Retrieved {len(briefs)} email briefs")
        
        # Step 4: Filter by company (synchronous, CPU-bound)
        filtered = filter_by_company(briefs, companies)
        matched_count = sum(len(emails) for emails in filtered.values())
        logger.info(f"Matched {matched_count} emails to {len(filtered)} companies")
        
        if not filtered:
            logger.info("No company-related emails found")
            await gmail.advance_pointer_after_processing(
                storage, last_id, pointer_key=cfg["POINTER_KEY"]
            )
            return
        
        # Step 5: Classify emails (synchronous, CPU-bound)
        classified = classify_latest(filtered)
        
        approve_count = sum(len(v) for v in classified.get("approve", {}).values())
        decline_count = sum(len(v) for v in classified.get("decline", {}).values())
        review_count = sum(len(v) for v in classified.get("review", {}).values())
        
        logger.info(
            f"Classification results: {approve_count} approved, "
            f"{decline_count} declined, {review_count} needs review"
        )
        
        # Step 6: Update Google Sheets (async)
        if approve_count or decline_count:
            await update_sheet_statuses(
                sheets=sheets,
                sheet_id=cfg["SHEET_ID"],
                sheet_tab=cfg["SHEET_TAB"],
                results=classified,
            )
            logger.info("Updated sheet statuses (column C)")
        
        if review_count:
            await update_sheet_review(
                sheets=sheets,
                sheet_id=cfg["SHEET_ID"],
                sheet_tab=cfg["SHEET_TAB"],
                results=classified,
            )
            logger.info("Updated review flags (column B)")
        
        # Step 7: Advance pointer (async)
        await gmail.advance_pointer_after_processing(
            storage, last_id, pointer_key=cfg["POINTER_KEY"]
        )
        logger.info("Pointer advanced successfully")
        
        logger.info("Async email processing completed successfully")
        
    except Exception as e:
        logger.exception(f"Error processing emails: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())

