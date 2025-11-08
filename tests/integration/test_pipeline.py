"""
Integration tests for pipeline.
"""

import pytest
from app.utils.filters import filter_by_company, classify_latest
from tests.mocks.gmail_mock import MockGmailClient
from tests.mocks.sheets_mock import MockSheetsClient
from app.storage.local_state import InMemoryEmailStorage


class TestPipelineIntegration:
    """Integration tests for the full pipeline."""

    def test_end_to_end_classification(self):
        """Test end-to-end classification flow."""
        # Setup mock clients
        companies_data = [
            (2, "Google Inc."),
            (3, "Microsoft Corporation"),
        ]
        sheets = MockSheetsClient(companies_data)

        # Mock emails (must contain company names for filtering to work)
        emails = [
            {
                "id": "msg1",
                "from": "hr@google.com",
                "subject": "Application Update from Google",
                "text_full": "Hello from Google. We are pleased to inform you that you have been selected for the next round of interviews.",
                "head": "Hello from Google. We are pleased to inform you that you have been selected.",
                "internalDate": "1234567890000",
                "threadId": "thread1",
            },
            {
                "id": "msg2",
                "from": "recruiter@microsoft.com",
                "subject": "Thank you for applying to Microsoft",
                "text_full": "Thank you for applying to Microsoft Corporation. Unfortunately, we have decided to move forward with other candidates at this time.",
                "head": "Thank you for applying to Microsoft Corporation. Unfortunately, we have decided to move forward with other candidates.",
                "internalDate": "1234567891000",
                "threadId": "thread2",
            },
        ]

        # Stage 1: Filter by company
        companies = [name for _, name in companies_data]
        filtered = filter_by_company(emails, companies)

        # Verify filtering
        assert "Google Inc." in filtered
        assert "Microsoft Corporation" in filtered
        assert len(filtered["Google Inc."]) == 1
        assert len(filtered["Microsoft Corporation"]) == 1

        # Stage 2: Classify
        classified = classify_latest(filtered)

        # Verify classification
        assert "Google Inc." in classified["approve"]
        assert "Microsoft Corporation" in classified["decline"]
        assert len(classified["approve"]["Google Inc."]) == 1
        assert len(classified["decline"]["Microsoft Corporation"]) == 1

    def test_review_classification(self):
        """Test classification as review when no clear signals."""
        companies_data = [(2, "Amazon")]
        companies = [name for _, name in companies_data]

        emails = [
            {
                "id": "msg1",
                "from": "hr@amazon.com",
                "subject": "Application Received from Amazon",
                "text_full": "Hello from Amazon. We have received your application and will review it in the coming weeks.",
                "head": "Hello from Amazon. We have received your application and will review it.",
                "internalDate": "1234567890000",
                "threadId": "thread1",
            }
        ]

        filtered = filter_by_company(emails, companies)
        classified = classify_latest(filtered)

        assert "Amazon" in classified["review"]
        assert "Amazon" not in classified["approve"]
        assert "Amazon" not in classified["decline"]

    def test_multiple_emails_selects_newest(self):
        """Test that newest email is selected when multiple emails exist."""
        companies_data = [(2, "Google Inc.")]
        companies = [name for _, name in companies_data]

        emails = [
            {
                "id": "msg1",
                "from": "hr@google.com",
                "subject": "Application Received from Google",
                "text_full": "Hello from Google. We received your application.",
                "head": "Hello from Google. We received your application.",
                "internalDate": "1234567890000",  # Older
                "threadId": "thread1",
            },
            {
                "id": "msg2",
                "from": "hr@google.com",
                "subject": "Interview Invitation from Google",
                "text_full": "Hello from Google. We are pleased to invite you to the next stage.",
                "head": "Hello from Google. We are pleased to invite you to the next stage.",
                "internalDate": "1234567891000",  # Newer
                "threadId": "thread2",
            },
        ]

        filtered = filter_by_company(emails, companies)
        classified = classify_latest(filtered)

        assert "Google Inc." in classified["approve"]
        # Should select msg2 (newer)
        assert classified["approve"]["Google Inc."][0]["id"] == "msg2"

