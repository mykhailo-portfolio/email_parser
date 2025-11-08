"""
Unit tests for filter utilities.
"""

import pytest
from app.utils.filters import should_skip, filter_by_company, classify_latest


class TestShouldSkip:
    """Tests for should_skip function."""

    def test_skip_job_alerts(self):
        """Test skipping job alert emails."""
        email = {
            "subject": "New Job Alert",
            "head": "Check out these new jobs",
        }
        assert should_skip(email) is True

    def test_skip_otp_messages(self):
        """Test skipping OTP/2FA messages."""
        email = {
            "subject": "Your verification code",
            "head": "Your code is 123456",
        }
        assert should_skip(email) is True

    def test_skip_linkedin_alerts(self):
        """Test skipping LinkedIn job alerts."""
        email = {
            "subject": "LinkedIn Jobs",
            "head": "New jobs you may be interested in",
        }
        assert should_skip(email) is True

    def test_dont_skip_normal_email(self):
        """Test that normal emails are not skipped."""
        email = {
            "subject": "Application Update",
            "head": "Thank you for your application",
        }
        assert should_skip(email) is False

    def test_dont_skip_company_response(self):
        """Test that company responses are not skipped."""
        email = {
            "subject": "Re: Your Application",
            "head": "We would like to invite you to an interview",
        }
        assert should_skip(email) is False


class TestFilterByCompany:
    """Tests for filter_by_company function."""

    def test_empty_inputs(self):
        """Test with empty inputs."""
        assert filter_by_company([], []) == {}
        assert filter_by_company([], ["Google"]) == {}
        assert filter_by_company([{"head": "test"}], []) == {}

    def test_match_in_head(self, sample_emails, sample_companies):
        """Test matching company name in email head."""
        emails = [
            {
                "id": "msg1",
                "head": "Thank you for applying to Google. We would like to interview you.",
                "text_full": "Thank you for applying to Google. We would like to interview you.",
                "subject": "Application",
            }
        ]
        result = filter_by_company(emails, ["Google Inc."])
        assert "Google Inc." in result
        assert len(result["Google Inc."]) == 1

    def test_match_in_body(self, sample_emails, sample_companies):
        """Test matching company name in email body when not in head."""
        emails = [
            {
                "id": "msg1",
                "head": "Thank you for your application.",
                "text_full": "Thank you for your application to Microsoft Corporation. We will review it.",
                "subject": "Application",
            }
        ]
        result = filter_by_company(emails, ["Microsoft Corporation"])
        assert "Microsoft Corporation" in result
        assert len(result["Microsoft Corporation"]) == 1

    def test_multiple_companies(self, sample_emails, sample_companies):
        """Test filtering with multiple companies."""
        emails = [
            {
                "id": "msg1",
                "head": "Thank you for applying to Google.",
                "text_full": "Thank you for applying to Google.",
                "subject": "Application",
            },
            {
                "id": "msg2",
                "head": "Thank you for applying to Microsoft Corporation.",
                "text_full": "Thank you for applying to Microsoft Corporation.",
                "subject": "Application",
            },
        ]
        result = filter_by_company(emails, ["Google Inc.", "Microsoft Corporation"])
        assert "Google Inc." in result
        assert "Microsoft Corporation" in result
        assert len(result["Google Inc."]) == 1
        assert len(result["Microsoft Corporation"]) == 1

    def test_skips_filtered_emails(self):
        """Test that emails matching skip patterns are filtered out."""
        emails = [
            {
                "id": "msg1",
                "head": "New job alert from Google",
                "text_full": "New job alert from Google",
                "subject": "Job Alert",
            }
        ]
        result = filter_by_company(emails, ["Google Inc."])
        # Should be empty because job alerts are skipped
        assert result == {}


class TestClassifyLatest:
    """Tests for classify_latest function."""

    def test_empty_input(self):
        """Test with empty input."""
        result = classify_latest({})
        assert result == {"approve": {}, "decline": {}, "review": {}}

    def test_classify_approve(self):
        """Test classification as approve."""
        emails = [
            {
                "id": "msg1",
                "head": "We are pleased to invite you to the next stage of our interview process.",
                "internalDate": "1234567890000",
            }
        ]
        result = classify_latest({"Company": emails})
        assert "Company" in result["approve"]
        assert "Company" not in result["decline"]
        assert "Company" not in result["review"]

    def test_classify_decline(self):
        """Test classification as decline."""
        emails = [
            {
                "id": "msg1",
                "head": "Unfortunately, we have decided to move forward with other candidates.",
                "internalDate": "1234567890000",
            }
        ]
        result = classify_latest({"Company": emails})
        assert "Company" in result["decline"]
        assert "Company" not in result["approve"]
        assert "Company" not in result["review"]

    def test_classify_review(self):
        """Test classification as review when no phrases found."""
        emails = [
            {
                "id": "msg1",
                "head": "We received your application and will review it.",
                "internalDate": "1234567890000",
            }
        ]
        result = classify_latest({"Company": emails})
        assert "Company" in result["review"]
        assert "Company" not in result["approve"]
        assert "Company" not in result["decline"]

    def test_selects_newest_email(self):
        """Test that the newest email is selected for classification."""
        emails = [
            {
                "id": "msg1",
                "head": "We received your application.",
                "internalDate": "1234567890000",  # Older
            },
            {
                "id": "msg2",
                "head": "We are pleased to invite you to the next stage.",
                "internalDate": "1234567891000",  # Newer
            },
        ]
        result = classify_latest({"Company": emails})
        assert "Company" in result["approve"]
        assert len(result["approve"]["Company"]) == 1
        assert result["approve"]["Company"][0]["id"] == "msg2"

    def test_first_hit_wins(self):
        """Test that first hit wins when both positive and negative phrases are present."""
        emails = [
            {
                "id": "msg1",
                "head": "We are pleased to inform you that you have been selected. Unfortunately, we have decided to move forward with other candidates.",
                "internalDate": "1234567890000",
            }
        ]
        result = classify_latest({"Company": emails})
        # "we are pleased to inform you" appears first, so should be approve
        assert "Company" in result["approve"]

    def test_multiple_companies(self):
        """Test classification with multiple companies."""
        filtered = {
            "Google": [
                {
                    "id": "msg1",
                    "head": "We are pleased to invite you to the next stage.",
                    "internalDate": "1234567890000",
                }
            ],
            "Microsoft": [
                {
                    "id": "msg2",
                    "head": "Unfortunately, we have decided to move forward with other candidates.",
                    "internalDate": "1234567891000",
                }
            ],
        }
        result = classify_latest(filtered)
        assert "Google" in result["approve"]
        assert "Microsoft" in result["decline"]

