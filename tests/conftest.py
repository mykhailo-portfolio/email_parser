"""
Pytest configuration and shared fixtures.
"""

import pytest
import sys
from pathlib import Path

# Add src to path for imports
PROJ_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJ_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


@pytest.fixture
def sample_email_brief():
    """Sample email brief for testing."""
    return {
        "id": "test_msg_123",
        "from": "recruiter@company.com",
        "subject": "Re: Application for Software Engineer",
        "text_full": "Thank you for your application. We would like to invite you to the next stage of our interview process.",
        "head": "Thank you for your application. We would like to invite you to the next stage.",
        "internalDate": "1234567890000",
        "threadId": "thread_123",
    }


@pytest.fixture
def sample_companies():
    """Sample company names for testing."""
    return [
        "Google Inc.",
        "Microsoft Corporation",
        "Amazon",
        "Meta Platforms",
    ]


@pytest.fixture
def sample_emails():
    """Sample list of email briefs for testing."""
    return [
        {
            "id": "msg1",
            "from": "hr@google.com",
            "subject": "Application Update",
            "text_full": "We are pleased to inform you that you have been selected for the next round.",
            "head": "We are pleased to inform you that you have been selected.",
            "internalDate": "1234567890000",
            "threadId": "thread1",
        },
        {
            "id": "msg2",
            "from": "recruiter@microsoft.com",
            "subject": "Thank you for applying",
            "text_full": "Unfortunately, we have decided to move forward with other candidates.",
            "head": "Unfortunately, we have decided to move forward with other candidates.",
            "internalDate": "1234567891000",
            "threadId": "thread2",
        },
        {
            "id": "msg3",
            "from": "jobs@amazon.com",
            "subject": "Your Application",
            "text_full": "We received your application and will review it shortly.",
            "head": "We received your application and will review it shortly.",
            "internalDate": "1234567892000",
            "threadId": "thread3",
        },
    ]

