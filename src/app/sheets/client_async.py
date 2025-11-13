"""
Async Google Sheets client.
"""

from __future__ import annotations
from typing import List, Tuple
import asyncio

from app.logging import logger
from app.utils.retry_async import async_retry_with_backoff
import gspread.exceptions


class AsyncSheetsClient:
    """
    Async wrapper around gspread client.
    Accepts an already authorized gspread client in ctor.
    """

    def __init__(self, gspread_client) -> None:
        self.gs = gspread_client

    @async_retry_with_backoff(max_retries=3, initial_delay=1.0, exceptions=(gspread.exceptions.APIError,))
    async def _open_spreadsheet(self, spreadsheet_id: str):
        """Open spreadsheet with retry logic (async)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.gs.open_by_key(spreadsheet_id)
        )

    async def fetch_pending_companies(
        self,
        spreadsheet_id: str,
        sheet_name: str,
        start_row: int
    ) -> List[Tuple[int, str]]:
        """
        Return list of (row_index, company_name) where:
          - column A (company) is non-empty
          - column C (status) is empty

        Args:
            spreadsheet_id: Google Sheets spreadsheet ID
            sheet_name: Name of the worksheet
            start_row: Starting row number (1-based)

        Returns:
            List of tuples (row_index, company_name)

        Raises:
            gspread.exceptions.APIError: If API call fails
            gspread.exceptions.WorksheetNotFound: If worksheet doesn't exist
        """
        try:
            sh = await self._open_spreadsheet(spreadsheet_id)
            
            # Run worksheet access and data fetch in thread pool
            loop = asyncio.get_event_loop()
            ws = await loop.run_in_executor(
                None,
                lambda: sh.worksheet(sheet_name)
            )
            
            rng = f"A{start_row}:C"
            rows = await loop.run_in_executor(
                None,
                lambda: ws.get(rng)
            )

            pending: List[Tuple[int, str]] = []
            for offset, row in enumerate(rows, start=start_row):
                company = row[0].strip() if len(row) > 0 and row[0] else ""
                status = row[2].strip() if len(row) > 2 and row[2] else ""

                if company and not status:
                    pending.append((offset, company))

            logger.debug(f"Found {len(pending)} pending companies in sheet '{sheet_name}'")
            return pending

        except gspread.exceptions.WorksheetNotFound as e:
            logger.error(f"Worksheet '{sheet_name}' not found in spreadsheet {spreadsheet_id}: {e}")
            raise
        except gspread.exceptions.APIError as e:
            logger.error(f"Google Sheets API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching companies: {e}")
            raise

