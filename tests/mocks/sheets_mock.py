"""
Mock Google Sheets API client for testing.
"""

from typing import List, Tuple, Optional
from app.sheets.client import SheetsClient


class MockGspreadClient:
    """Mock gspread client."""

    def __init__(self, companies: Optional[List[Tuple[int, str]]] = None):
        """
        Initialize mock client.

        Args:
            companies: List of (row_index, company_name) tuples
        """
        self.companies = companies or []

    def open_by_key(self, spreadsheet_id: str):
        """Return mock spreadsheet."""
        return MockSpreadsheet(self.companies)


class MockSpreadsheet:
    """Mock spreadsheet."""

    def __init__(self, companies: List[Tuple[int, str]]):
        self.companies = companies

    def worksheet(self, sheet_name: str):
        """Return mock worksheet."""
        return MockWorksheet(self.companies)


class MockWorksheet:
    """Mock worksheet."""

    def __init__(self, companies: List[Tuple[int, str]]):
        self.companies = companies

    def get(self, range_name: str):
        """Return mock data based on range."""
        # Return rows: [company, link, status]
        rows = []
        for row_idx, company_name in self.companies:
            rows.append([company_name, "", ""])  # Empty link and status
        return rows

    def get_all_values(self):
        """Return all values as 2D list."""
        rows = [["Company", "Link", "Status"]]  # Header
        for row_idx, company_name in self.companies:
            rows.append([company_name, "", ""])
        return rows

    def update(self, range_name: str, values: List[List[str]], value_input_option: str = None):
        """Mock update method."""
        pass


class MockSheetsClient(SheetsClient):
    """Mock Sheets client for testing."""

    def __init__(self, companies: Optional[List[Tuple[int, str]]] = None):
        """
        Initialize mock client.

        Args:
            companies: List of (row_index, company_name) tuples
        """
        mock_gspread = MockGspreadClient(companies)
        super().__init__(mock_gspread)

