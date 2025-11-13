from __future__ import annotations
from typing import List, Tuple
from app.logging import logger
from app.utils.retry import retry_with_backoff
import gspread.exceptions


class SheetsClient:
    """
    Thin wrapper around gspread client.
    Accepts an already authorized gspread client in ctor.
    """

    def __init__(self, gspread_client) -> None:
        self.gs = gspread_client

    @retry_with_backoff(max_retries=3, initial_delay=1.0, exceptions=(gspread.exceptions.APIError,))
    def _open_spreadsheet(self, spreadsheet_id: str):
        """Open spreadsheet with retry logic."""
        return self.gs.open_by_key(spreadsheet_id)

    def fetch_pending_companies(
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
            sh = self._open_spreadsheet(spreadsheet_id)
            ws = sh.worksheet(sheet_name)

            rng = f"A{start_row}:C"
            rows = ws.get(rng)

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