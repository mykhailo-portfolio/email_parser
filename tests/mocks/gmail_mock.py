"""
Mock Gmail API client for testing.
"""

from typing import List, Dict, Optional
from app.gmail.client import GmailClient


class MockGmailService:
    """Mock Gmail API service."""

    def __init__(self, messages: Optional[List[Dict]] = None):
        """
        Initialize mock service with test messages.

        Args:
            messages: List of message dictionaries to return
        """
        self.messages = messages or []
        self.users_called = False

    def users(self):
        """Return mock users resource."""
        return MockUsersResource(self.messages)


class MockUsersResource:
    """Mock users resource."""

    def __init__(self, messages: List[Dict]):
        self.messages = messages

    def messages(self):
        """Return mock messages resource."""
        return MockMessagesResource(self.messages)


class MockMessagesResource:
    """Mock messages resource."""

    def __init__(self, messages: List[Dict]):
        self.messages = messages
        self._list_response = {
            "messages": [{"id": msg.get("id", f"msg_{i}")} for i, msg in enumerate(messages)],
        }

    def list(self, **kwargs):
        """Mock list method."""
        return MockRequest(self._list_response)

    def get(self, **kwargs):
        """Mock get method."""
        msg_id = kwargs.get("id")
        # Find message by ID
        for msg in self.messages:
            if msg.get("id") == msg_id:
                return MockRequest(msg)
        # Return default if not found
        return MockRequest({
            "id": msg_id,
            "payload": {
                "headers": [
                    {"name": "From", "value": "test@example.com"},
                    {"name": "Subject", "value": "Test"},
                ],
                "body": {"data": ""},
            },
            "internalDate": "1234567890000",
        })


class MockRequest:
    """Mock request object that returns data when execute() is called."""

    def __init__(self, data: Dict):
        self.data = data

    def execute(self):
        """Return mock data."""
        return self.data


class MockGmailClient(GmailClient):
    """Mock Gmail client for testing."""

    def __init__(self, messages: Optional[List[Dict]] = None):
        """
        Initialize mock client.

        Args:
            messages: List of message dictionaries to return
        """
        mock_service = MockGmailService(messages)
        super().__init__(mock_service)

    def get_message_briefs(self, ids: List[str]) -> List[Dict]:
        """
        Return mock message briefs.

        Args:
            ids: List of message IDs

        Returns:
            List of message brief dictionaries
        """
        # Return briefs for requested IDs
        briefs = []
        for msg_id in ids:
            brief = {
                "id": msg_id,
                "from": "test@example.com",
                "subject": "Test Subject",
                "text_full": "Test full text",
                "head": "Test head",
                "internalDate": "1234567890000",
                "threadId": "thread_123",
            }
            briefs.append(brief)
        return briefs

