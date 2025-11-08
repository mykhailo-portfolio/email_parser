"""
Unit tests for authentication logic.
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError

from app.auth import (
    ensure_valid_credentials,
    reauthorize_token,
    TokenExpiredError,
)


class TestEnsureValidCredentials:
    """Test cases for ensure_valid_credentials."""

    def test_valid_credentials(self, tmp_path):
        """Test that valid credentials are returned as-is."""
        token_file = tmp_path / "token.json"
        
        # Create a valid token file
        token_data = {
            "token": "valid_access_token",
            "refresh_token": "valid_refresh_token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
            "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
        }
        token_file.write_text(json.dumps(token_data))
        
        # Mock Credentials.from_authorized_user_file to return valid creds
        with patch("app.auth.Credentials.from_authorized_user_file") as mock_from_file:
            mock_creds = Mock(spec=Credentials)
            mock_creds.valid = True
            mock_creds.expired = False
            mock_creds.refresh_token = "valid_refresh_token"
            mock_from_file.return_value = mock_creds
            
            result = ensure_valid_credentials(
                token_path=str(token_file),
                scopes=["https://www.googleapis.com/auth/gmail.readonly"],
                auto_reauthorize=False,
            )
            
            assert result is mock_creds
            assert result.valid is True

    def test_refresh_expired_token(self, tmp_path):
        """Test refreshing expired token."""
        token_file = tmp_path / "token.json"
        
        token_data = {
            "token": "expired_access_token",
            "refresh_token": "valid_refresh_token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
            "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
        }
        token_file.write_text(json.dumps(token_data))
        
        with patch("app.auth.Credentials.from_authorized_user_file") as mock_from_file, \
             patch("google.auth.transport.requests.Request") as mock_request:
            
            mock_creds = Mock(spec=Credentials)
            mock_creds.valid = False
            mock_creds.expired = True
            mock_creds.refresh_token = "valid_refresh_token"
            mock_creds.to_json.return_value = json.dumps({
                **token_data,
                "token": "new_access_token",
            })
            mock_from_file.return_value = mock_creds
            
            # Mock refresh to succeed
            mock_creds.refresh = Mock()
            
            result = ensure_valid_credentials(
                token_path=str(token_file),
                scopes=["https://www.googleapis.com/auth/gmail.readonly"],
                auto_reauthorize=False,
            )
            
            assert result is mock_creds
            mock_creds.refresh.assert_called_once()
            # Verify token was saved
            saved_data = json.loads(token_file.read_text())
            assert saved_data["token"] == "new_access_token"

    def test_refresh_fails_raises_error(self, tmp_path):
        """Test that RefreshError is raised when refresh fails."""
        token_file = tmp_path / "token.json"
        
        token_data = {
            "token": "expired_access_token",
            "refresh_token": "invalid_refresh_token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
            "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
        }
        token_file.write_text(json.dumps(token_data))
        
        with patch("app.auth.Credentials.from_authorized_user_file") as mock_from_file, \
             patch("google.auth.transport.requests.Request"):
            
            mock_creds = Mock(spec=Credentials)
            mock_creds.valid = False
            mock_creds.expired = True
            mock_creds.refresh_token = "invalid_refresh_token"
            mock_from_file.return_value = mock_creds
            
            # Mock refresh to fail
            mock_creds.refresh = Mock(side_effect=RefreshError("Token expired"))
            
            with pytest.raises(TokenExpiredError) as exc_info:
                ensure_valid_credentials(
                    token_path=str(token_file),
                    scopes=["https://www.googleapis.com/auth/gmail.readonly"],
                    auto_reauthorize=False,
                )
            
            assert "Token refresh failed" in str(exc_info.value)

    def test_refresh_fails_auto_reauthorize(self, tmp_path):
        """Test that auto_reauthorize triggers re-authorization on refresh failure."""
        token_file = tmp_path / "token.json"
        
        token_data = {
            "token": "expired_access_token",
            "refresh_token": "invalid_refresh_token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
            "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
        }
        token_file.write_text(json.dumps(token_data))
        
        with patch("app.auth.Credentials.from_authorized_user_file") as mock_from_file, \
             patch("google.auth.transport.requests.Request"), \
             patch("app.auth.reauthorize_token") as mock_reauth:
            
            mock_creds = Mock(spec=Credentials)
            mock_creds.valid = False
            mock_creds.expired = True
            mock_creds.refresh_token = "invalid_refresh_token"
            mock_from_file.return_value = mock_creds
            
            # Mock refresh to fail
            mock_creds.refresh = Mock(side_effect=RefreshError("Token expired"))
            
            # Mock reauthorize to return new creds
            new_creds = Mock(spec=Credentials)
            new_creds.valid = True
            mock_reauth.return_value = new_creds
            
            result = ensure_valid_credentials(
                token_path=str(token_file),
                scopes=["https://www.googleapis.com/auth/gmail.readonly"],
                auto_reauthorize=True,
            )
            
            assert result is new_creds
            mock_reauth.assert_called_once()

    def test_no_refresh_token_raises_error(self, tmp_path):
        """Test that TokenExpiredError is raised when no refresh token exists."""
        token_file = tmp_path / "token.json"
        
        token_data = {
            "token": "expired_access_token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
            "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
        }
        token_file.write_text(json.dumps(token_data))
        
        with patch("app.auth.Credentials.from_authorized_user_file") as mock_from_file:
            mock_creds = Mock(spec=Credentials)
            mock_creds.valid = False
            mock_creds.expired = True
            mock_creds.refresh_token = None
            mock_from_file.return_value = mock_creds
            
            with pytest.raises(TokenExpiredError) as exc_info:
                ensure_valid_credentials(
                    token_path=str(token_file),
                    scopes=["https://www.googleapis.com/auth/gmail.readonly"],
                    auto_reauthorize=False,
                )
            
            assert "No refresh token" in str(exc_info.value)

    def test_no_refresh_token_auto_reauthorize(self, tmp_path):
        """Test that auto_reauthorize triggers re-authorization when no refresh token."""
        token_file = tmp_path / "token.json"
        
        token_data = {
            "token": "expired_access_token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
            "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
        }
        token_file.write_text(json.dumps(token_data))
        
        with patch("app.auth.Credentials.from_authorized_user_file") as mock_from_file, \
             patch("app.auth.reauthorize_token") as mock_reauth:
            
            mock_creds = Mock(spec=Credentials)
            mock_creds.valid = False
            mock_creds.expired = True
            mock_creds.refresh_token = None
            mock_from_file.return_value = mock_creds
            
            # Mock reauthorize to return new creds
            new_creds = Mock(spec=Credentials)
            new_creds.valid = True
            mock_reauth.return_value = new_creds
            
            result = ensure_valid_credentials(
                token_path=str(token_file),
                scopes=["https://www.googleapis.com/auth/gmail.readonly"],
                auto_reauthorize=True,
            )
            
            assert result is new_creds
            mock_reauth.assert_called_once()

    def test_file_not_found_raises_error(self, tmp_path):
        """Test that FileNotFoundError is raised when token file doesn't exist."""
        token_file = tmp_path / "nonexistent_token.json"
        
        with pytest.raises(FileNotFoundError) as exc_info:
            ensure_valid_credentials(
                token_path=str(token_file),
                scopes=["https://www.googleapis.com/auth/gmail.readonly"],
                auto_reauthorize=False,
            )
        
        assert "Token file not found" in str(exc_info.value)

    def test_file_not_found_auto_reauthorize(self, tmp_path):
        """Test that auto_reauthorize triggers re-authorization when file doesn't exist."""
        token_file = tmp_path / "nonexistent_token.json"
        
        with patch("app.auth.reauthorize_token") as mock_reauth:
            new_creds = Mock(spec=Credentials)
            new_creds.valid = True
            mock_reauth.return_value = new_creds
            
            result = ensure_valid_credentials(
                token_path=str(token_file),
                scopes=["https://www.googleapis.com/auth/gmail.readonly"],
                auto_reauthorize=True,
            )
            
            assert result is new_creds
            mock_reauth.assert_called_once()


class TestReauthorizeToken:
    """Test cases for reauthorize_token."""

    def test_reauthorize_success(self, tmp_path):
        """Test successful re-authorization."""
        token_file = tmp_path / "new_token.json"
        client_secrets = tmp_path / "client_secret.json"
        
        # Create client secrets file
        client_secrets.write_text(json.dumps({
            "installed": {
                "client_id": "test_client_id",
                "client_secret": "test_client_secret",
            }
        }))
        
        with patch("app.auth.InstalledAppFlow") as mock_flow_class:
            mock_flow = Mock()
            mock_flow_class.from_client_secrets_file.return_value = mock_flow
            
            mock_creds = Mock(spec=Credentials)
            mock_creds.refresh_token = "new_refresh_token"
            mock_creds.to_json.return_value = json.dumps({
                "token": "new_access_token",
                "refresh_token": "new_refresh_token",
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_id": "test_client_id",
                "client_secret": "test_client_secret",
                "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
            })
            mock_flow.run_local_server.return_value = mock_creds
            
            result = reauthorize_token(
                token_path=str(token_file),
                scopes=["https://www.googleapis.com/auth/gmail.readonly"],
                client_secrets_path=str(client_secrets),
            )
            
            assert result is mock_creds
            assert token_file.exists()
            saved_data = json.loads(token_file.read_text())
            assert saved_data["refresh_token"] == "new_refresh_token"

    def test_reauthorize_no_client_secrets(self, tmp_path):
        """Test that FileNotFoundError is raised when client secrets file doesn't exist."""
        token_file = tmp_path / "new_token.json"
        client_secrets = tmp_path / "nonexistent_client_secret.json"
        
        with pytest.raises(FileNotFoundError) as exc_info:
            reauthorize_token(
                token_path=str(token_file),
                scopes=["https://www.googleapis.com/auth/gmail.readonly"],
                client_secrets_path=str(client_secrets),
            )
        
        assert "Client secrets file not found" in str(exc_info.value)

