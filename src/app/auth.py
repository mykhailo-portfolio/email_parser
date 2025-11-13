"""
OAuth authentication utilities with automatic re-authorization support.
"""

from __future__ import annotations
import os
import sys
import json
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError
from google_auth_oauthlib.flow import InstalledAppFlow
from app.logging import logger

load_dotenv()


class TokenExpiredError(Exception):
    """Raised when OAuth token cannot be refreshed and needs re-authorization."""
    pass


def reauthorize_token(
    token_path: str,
    scopes: list[str],
    client_secrets_path: Optional[str] = None,
) -> Credentials:
    """
    Perform OAuth re-authorization flow and save new token.

    Args:
        token_path: Path where to save the new token file
        scopes: List of OAuth scopes required
        client_secrets_path: Path to client_secrets.json. If None, uses GOOGLE_CLIENT_SECRETS env var.

    Returns:
        New Credentials object

    Raises:
        FileNotFoundError: If client_secrets file doesn't exist
        Exception: If authorization flow fails
    """
    if client_secrets_path is None:
        client_secrets_path = os.getenv(
            "GOOGLE_CLIENT_SECRETS",
            "./credentials/client_secret.json"
        )

    client_secrets = Path(client_secrets_path)
    if not client_secrets.exists():
        raise FileNotFoundError(
            f"Client secrets file not found: {client_secrets}. "
            f"Please set GOOGLE_CLIENT_SECRETS environment variable or place client_secret.json in credentials/"
        )

    token_file = Path(token_path)
    token_file.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Starting OAuth re-authorization flow for {token_path}...")
    logger.info("A browser window will open. Please complete the authorization.")

    try:
        # Create flow with offline access to get refresh token
        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_secrets),
            scopes
        )
        # run_local_server automatically requests offline access (access_type=offline)
        creds = flow.run_local_server(port=0)
        
        # Verify we got a refresh token
        if not creds.refresh_token:
            logger.warning(
                "⚠️  No refresh token received. This may happen if you've already authorized this app. "
                "For server use, you need a refresh token. Try revoking access at "
                "https://myaccount.google.com/permissions and re-authorizing."
            )
        else:
            logger.info(f"✅ Refresh token received and will be saved")
        
        # Save token (creds.to_json() includes refresh_token if present)
        token_file.write_text(creds.to_json(), encoding="utf-8")
        
        # Verify refresh token was saved
        saved_data = json.loads(token_file.read_text())
        if saved_data.get("refresh_token"):
            logger.info(f"✅ New token saved to {token_path} (includes refresh token)")
        else:
            logger.warning(f"⚠️  Token saved but refresh_token not found in saved file for {token_path}")
        
        return creds
    except Exception as e:
        logger.error(f"❌ OAuth re-authorization failed: {e}")
        raise


def ensure_valid_credentials(
    token_path: str,
    scopes: list[str],
    auto_reauthorize: bool = False,
) -> Credentials:
    """
    Load credentials and refresh if needed. Optionally re-authorize if refresh fails.

    Args:
        token_path: Path to token JSON file
        scopes: List of OAuth scopes required
        auto_reauthorize: If True, automatically start re-authorization flow on refresh failure.
                         If False, raises TokenExpiredError.

    Returns:
        Valid Credentials object

    Raises:
        FileNotFoundError: If token file doesn't exist
        TokenExpiredError: If refresh fails and auto_reauthorize is False
    """
    token_file = Path(token_path)
    if not token_file.exists():
        if auto_reauthorize:
            logger.warning(f"Token file not found: {token_path}. Starting re-authorization...")
            return reauthorize_token(token_path, scopes)
        raise FileNotFoundError(f"Token file not found: {token_path}")

    creds = Credentials.from_authorized_user_file(str(token_file), scopes)

    # If credentials are valid, return them
    if creds.valid:
        return creds

    # Try to refresh if expired
    if creds.expired and creds.refresh_token:
        try:
            from google.auth.transport.requests import Request
            # Store refresh token before refresh (in case Google returns a new one)
            old_refresh_token = creds.refresh_token
            creds.refresh(Request())
            
            # Save refreshed token (includes new access token and potentially new refresh token)
            try:
                token_file.write_text(creds.to_json(), encoding="utf-8")
                # Log refresh token status
                if creds.refresh_token:
                    if creds.refresh_token != old_refresh_token:
                        logger.info(f"✅ Credentials refreshed for {token_path} (new refresh token received)")
                    else:
                        logger.debug(f"✅ Credentials refreshed for {token_path}")
                else:
                    logger.warning(f"⚠️  Credentials refreshed but no refresh token in response for {token_path}")
            except OSError as e:
                # Handle read-only file system (e.g., in Docker with read-only volume)
                if e.errno == 30:  # Read-only file system
                    logger.warning(
                        f"⚠️  Credentials refreshed but cannot save to {token_path} (read-only file system). "
                        f"Token will work until expiration. Consider mounting credentials volume as writable."
                    )
                else:
                    # Re-raise other OSErrors
                    raise
            return creds
        except RefreshError as e:
            logger.error(
                f"❌ Token refresh failed for {token_path}: {e}\n"
                f"   The refresh token has expired or been revoked."
            )
            if auto_reauthorize:
                logger.info("🔄 Attempting automatic re-authorization...")
                return reauthorize_token(token_path, scopes)
            else:
                raise TokenExpiredError(
                    f"Token refresh failed for {token_path}. "
                    f"Please run 'python scripts/bootstrap_oauth.py' to re-authorize."
                ) from e
        except Exception as e:
            logger.error(f"❌ Unexpected error refreshing credentials: {e}")
            raise

    # If no refresh token, need to re-authorize
    if not creds.refresh_token:
        logger.warning(f"No refresh token found for {token_path}. Re-authorization required.")
        if auto_reauthorize:
            return reauthorize_token(token_path, scopes)
        else:
            raise TokenExpiredError(
                f"No refresh token for {token_path}. "
                f"Please run 'python scripts/bootstrap_oauth.py' to re-authorize."
            )

    return creds

