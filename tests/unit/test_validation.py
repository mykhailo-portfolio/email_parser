"""
Unit tests for validation utilities.
"""

import pytest
from app.utils.validation import (
    validate_email_brief,
    validate_company_name,
    validate_message_ids,
    validate_sheet_id,
    validate_row_number,
)


class TestValidateEmailBrief:
    """Tests for validate_email_brief function."""

    def test_valid_email_brief(self):
        """Test validation of valid email brief."""
        email = {
            "id": "msg123",
            "from": "sender@example.com",
            "subject": "Test",
            "text_full": "Full text",
            "head": "Head text",
            "internalDate": "1234567890",
        }
        assert validate_email_brief(email) is True

    def test_missing_required_field(self):
        """Test validation fails when required field is missing."""
        email = {
            "id": "msg123",
            "from": "sender@example.com",
            # Missing "subject"
            "text_full": "Full text",
            "head": "Head text",
            "internalDate": "1234567890",
        }
        assert validate_email_brief(email) is False

    def test_invalid_id(self):
        """Test validation fails with invalid ID."""
        email = {
            "id": "",  # Empty ID
            "from": "sender@example.com",
            "subject": "Test",
            "text_full": "Full text",
            "head": "Head text",
            "internalDate": "1234567890",
        }
        assert validate_email_brief(email) is False

    def test_not_dict(self):
        """Test validation fails when input is not a dictionary."""
        assert validate_email_brief("not a dict") is False
        assert validate_email_brief(None) is False
        assert validate_email_brief([]) is False


class TestValidateCompanyName:
    """Tests for validate_company_name function."""

    def test_valid_company_name(self):
        """Test validation of valid company name."""
        assert validate_company_name("Google") is True
        assert validate_company_name("Microsoft Corporation") is True

    def test_empty_string(self):
        """Test validation fails with empty string."""
        assert validate_company_name("") is False
        assert validate_company_name("   ") is False

    def test_not_string(self):
        """Test validation fails when input is not a string."""
        assert validate_company_name(123) is False
        assert validate_company_name(None) is False
        assert validate_company_name([]) is False

    def test_too_long(self):
        """Test validation fails with too long company name."""
        long_name = "A" * 201
        assert validate_company_name(long_name) is False


class TestValidateMessageIds:
    """Tests for validate_message_ids function."""

    def test_valid_message_ids(self):
        """Test validation of valid message IDs."""
        assert validate_message_ids(["msg1", "msg2", "msg3"]) is True
        assert validate_message_ids([]) is True  # Empty list is valid

    def test_invalid_message_id(self):
        """Test validation fails with invalid message ID."""
        assert validate_message_ids(["msg1", "", "msg3"]) is False
        assert validate_message_ids(["msg1", None, "msg3"]) is False

    def test_not_list(self):
        """Test validation fails when input is not a list."""
        assert validate_message_ids("not a list") is False
        assert validate_message_ids(None) is False


class TestValidateSheetId:
    """Tests for validate_sheet_id function."""

    def test_valid_sheet_id(self):
        """Test validation of valid sheet ID."""
        # Typical Google Sheet ID is 44 characters
        valid_id = "1" * 44
        assert validate_sheet_id(valid_id) is True

    def test_empty_string(self):
        """Test validation fails with empty string."""
        assert validate_sheet_id("") is False
        assert validate_sheet_id("   ") is False

    def test_not_string(self):
        """Test validation fails when input is not a string."""
        assert validate_sheet_id(123) is False
        assert validate_sheet_id(None) is False

    def test_too_short(self):
        """Test validation fails with too short sheet ID."""
        assert validate_sheet_id("123") is False

    def test_too_long(self):
        """Test validation fails with too long sheet ID."""
        long_id = "1" * 101
        assert validate_sheet_id(long_id) is False


class TestValidateRowNumber:
    """Tests for validate_row_number function."""

    def test_valid_row_number(self):
        """Test validation of valid row number."""
        assert validate_row_number(1) is True
        assert validate_row_number(100) is True
        assert validate_row_number(1000) is True

    def test_below_minimum(self):
        """Test validation fails when row is below minimum."""
        assert validate_row_number(0) is False
        assert validate_row_number(-1) is False

    def test_not_integer(self):
        """Test validation fails when input is not an integer."""
        assert validate_row_number("1") is False
        assert validate_row_number(1.5) is False
        assert validate_row_number(None) is False

    def test_too_large(self):
        """Test validation fails with too large row number."""
        assert validate_row_number(2000000) is False

