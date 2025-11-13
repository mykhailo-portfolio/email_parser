"""
Async sheet writer for updating application statuses.
"""

from __future__ import annotations
from typing import Dict, List
import asyncio

from app.sheets.client_async import AsyncSheetsClient
from app.logging import logger
from app.utils.retry_async import async_retry_with_backoff


async def update_sheet_statuses(
    sheets: AsyncSheetsClient,
    sheet_id: str,
    sheet_tab: str,
    results: Dict[str, Dict[str, List[dict]]],
) -> None:
    """
    Write classification results into the Google Sheet (async).

    Args:
        sheets (AsyncSheetsClient): Initialized AsyncSheetsClient.
        sheet_id (str): Target spreadsheet ID.
        sheet_tab (str): Target worksheet name.
        results (dict): Output of classify_first_hit(), e.g.:
            {"approve": {company: [emails]}, "decline": {...}, "review": {...}}
    """
    try:
        loop = asyncio.get_event_loop()
        
        # Open spreadsheet and worksheet
        sh = await sheets._open_spreadsheet(sheet_id)
        ws = await loop.run_in_executor(
            None,
            lambda: sh.worksheet(sheet_tab)
        )

        # Read all values as a 2D list (no header parsing).
        # Expectation: Column A = Company, Column C = Status.
        rows = await loop.run_in_executor(
            None,
            lambda: ws.get_all_values()
        )
        
        if not rows:
            logger.warning("Worksheet is empty; nothing to update")
            return

        # Build index: {company_lower: row_index} (1-based row index in sheet)
        # Skip header row (assume first row is header-like).
        index: Dict[str, int] = {}
        for i, row in enumerate(rows, start=1):
            if i == 1:
                continue  # header row
            company_cell = (row[0] if len(row) >= 1 else "").strip().lower()
            if company_cell:
                # keep first occurrence; if duplicates exist, first wins
                index.setdefault(company_cell, i)

        # Prepare updates for approve/decline only
        def _label(bucket: str) -> str:
            return "Approved" if bucket == "approve" else "Declined"

        updates: List[tuple[int, str]] = []
        for bucket in ("approve", "decline"):
            companies = results.get(bucket, {}) or {}
            for company in companies.keys():
                key = (company or "").strip().lower()
                row_idx = index.get(key)
                if row_idx:
                    updates.append((row_idx, _label(bucket)))

        if not updates:
            logger.warning("No matching company rows found to update")
            return

        # Use batch_update for better performance (up to 100 updates per batch)
        BATCH_SIZE = 100
        total_updated = 0
        
        @async_retry_with_backoff(max_retries=3, initial_delay=1.0)
        async def _batch_update(batch_updates: List[dict]) -> None:
            """Update multiple cells in a single API call."""
            await loop.run_in_executor(
                None,
                lambda: ws.batch_update(batch_updates, value_input_option="USER_ENTERED")
            )
        
        # Group updates into batches
        for i in range(0, len(updates), BATCH_SIZE):
            batch = updates[i:i + BATCH_SIZE]
            batch_updates = [
                {
                    "range": f"C{row_idx}",
                    "values": [[label]]
                }
                for row_idx, label in batch
            ]
            
            try:
                await _batch_update(batch_updates)
                total_updated += len(batch)
            except Exception as e:
                logger.error(f"Batch update failed for {len(batch)} rows: {e}")
                # Fallback to individual updates for this batch
                logger.warning("Falling back to individual updates for failed batch")
                for row_idx, label in batch:
                    try:
                        @async_retry_with_backoff(max_retries=3, initial_delay=1.0)
                        async def _update_row(row_idx: int, label: str) -> None:
                            await loop.run_in_executor(
                                None,
                                lambda: ws.update(f"C{row_idx}", [[label]], value_input_option="USER_ENTERED")
                            )
                        await _update_row(row_idx, label)
                        total_updated += 1
                    except Exception as e2:
                        logger.error(f"Failed to update row {row_idx} with label '{label}': {e2}")
                        raise

        logger.info(f"Updated {total_updated} rows in column C")

    except Exception as e:
        logger.error(f"Sheet status update failed: {e}")
        raise


async def update_sheet_review(
    sheets: AsyncSheetsClient,
    sheet_id: str,
    sheet_tab: str,
    results: dict,
) -> None:
    """
    Write 'Needs review' into column B for companies classified as review (async).
    Does NOT overwrite existing statuses in column C.

    Args:
        sheets (AsyncSheetsClient): Async sheets client.
        sheet_id (str): Spreadsheet ID.
        sheet_tab (str): Worksheet name.
        results (dict): Output of classify_latest_with_review().
    """
    try:
        loop = asyncio.get_event_loop()
        
        # Open spreadsheet and worksheet
        sh = await sheets._open_spreadsheet(sheet_id)
        ws = await loop.run_in_executor(
            None,
            lambda: sh.worksheet(sheet_tab)
        )
        
        rows = await loop.run_in_executor(
            None,
            lambda: ws.get_all_values()
        )
        
        if not rows:
            logger.warning("Worksheet is empty; nothing to update (review)")
            return

        # Build index by company in column A (case-insensitive)
        index = {}
        for i, row in enumerate(rows, start=1):
            if i == 1:
                continue  # header
            company = (row[0] if len(row) >= 1 else "").strip().lower()
            if company:
                index.setdefault(company, i)

        review = results.get("review", {}) or {}
        if not review:
            logger.debug("No review entries to process")
            return

        updates = []
        for company in review.keys():
            key = (company or "").strip().lower()
            row_idx = index.get(key)
            if not row_idx:
                continue
            # Skip if column C already has a status (do not override decisions)
            col_c = rows[row_idx - 1][2] if len(rows[row_idx - 1]) >= 3 else ""
            if col_c and col_c.strip():
                continue
            updates.append(row_idx)

        if not updates:
            logger.debug("No rows eligible for review flag")
            return

        # Use batch_update for better performance (up to 100 updates per batch)
        BATCH_SIZE = 100
        total_updated = 0
        
        @async_retry_with_backoff(max_retries=3, initial_delay=1.0)
        async def _batch_update(batch_updates: List[dict]) -> None:
            """Update multiple cells in a single API call."""
            await loop.run_in_executor(
                None,
                lambda: ws.batch_update(batch_updates, value_input_option="USER_ENTERED")
            )
        
        # Group updates into batches
        for i in range(0, len(updates), BATCH_SIZE):
            batch = updates[i:i + BATCH_SIZE]
            batch_updates = [
                {
                    "range": f"B{row_idx}",
                    "values": [["Needs review"]]
                }
                for row_idx in batch
            ]
            
            try:
                await _batch_update(batch_updates)
                total_updated += len(batch)
            except Exception as e:
                logger.error(f"Batch update failed for {len(batch)} review flags: {e}")
                # Fallback to individual updates for this batch
                logger.warning("Falling back to individual updates for failed batch")
                for row_idx in batch:
                    try:
                        @async_retry_with_backoff(max_retries=3, initial_delay=1.0)
                        async def _update_review_flag(row_idx: int) -> None:
                            await loop.run_in_executor(
                                None,
                                lambda: ws.update(f"B{row_idx}", [["Needs review"]], value_input_option="USER_ENTERED")
                            )
                        await _update_review_flag(row_idx)
                        total_updated += 1
                    except Exception as e2:
                        logger.error(f"Failed to update review flag for row {row_idx}: {e2}")
                        raise

        logger.info(f"Review flags written to {total_updated} rows in column B")
    except Exception as e:
        logger.error(f"Sheet review update failed: {e}")
        raise

