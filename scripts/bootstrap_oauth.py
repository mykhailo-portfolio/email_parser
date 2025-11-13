import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

load_dotenv()

# Paths
CLIENT_SECRETS = Path(os.getenv("GOOGLE_CLIENT_SECRETS", "./credentials/client_secret.json"))
CRED_DIR       = CLIENT_SECRETS.parent
GMAIL_TOKEN    = Path(os.getenv("GOOGLE_GMAIL_TOKEN",   "./credentials/token_gmail.json"))
SHEETS_TOKEN   = Path(os.getenv("GOOGLE_SHEETS_TOKEN",  "./credentials/token_sheets.json"))

# Scopes (separate per API)
GMAIL_SCOPES  = [s.strip() for s in os.getenv("GOOGLE_GMAIL_SCOPES").split(",") if s.strip()]

SHEETS_SCOPES = [s.strip() for s in os.getenv("GOOGLE_SHEETS_SCOPES").split(",") if s.strip()]

# Optional: quick Sheet check
SHEET_ID  = os.getenv("GOOGLE_SHEET_ID", "")
WORKSHEET = os.getenv("SHEET_WORKSHEET", "Applications")


def ensure_token(token_path: Path, scopes: list[str]) -> Credentials:
    """
    Create/refresh a token.json for the given scopes.
    
    Args:
        token_path: Path where to save the token file
        scopes: List of OAuth scopes required
        
    Returns:
        Valid Credentials object
        
    Raises:
        FileNotFoundError: If client_secrets file doesn't exist
        Exception: If authorization flow fails
    """
    token_path.parent.mkdir(parents=True, exist_ok=True)
    creds = None

    # Try to load existing token
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), scopes)
            print(f"[INFO] Loaded existing token from {token_path}")
        except Exception as e:
            print(f"[WARN] Failed to load existing token: {e}")
            creds = None

    # Check if credentials are valid
    if creds and creds.valid:
        print(f"[OK] Token is valid for {token_path}")
        return creds

    # Try to refresh if expired
    if creds and creds.expired and creds.refresh_token:
        try:
            from google.auth.transport.requests import Request
            print(f"[INFO] Token expired, attempting to refresh using refresh token...")
            old_refresh_token = creds.refresh_token
            creds.refresh(Request())
            # Save refreshed token (may include new refresh token from Google)
            token_path.write_text(creds.to_json(), encoding="utf-8")
            if creds.refresh_token:
                if creds.refresh_token != old_refresh_token:
                    print(f"[OK] Token refreshed successfully (new refresh token received)")
                else:
                    print(f"[OK] Token refreshed successfully")
            else:
                print(f"[WARN] Token refreshed but no refresh token in response")
            return creds
        except Exception as e:
            print(f"[WARN] Token refresh failed: {e}")
            print(f"[INFO] Will start new authorization flow...")
            creds = None

    # Need to get new token via OAuth flow
    if not CLIENT_SECRETS.exists():
        raise FileNotFoundError(
            f"Client secrets file not found: {CLIENT_SECRETS}\n"
            f"Please ensure GOOGLE_CLIENT_SECRETS environment variable points to client_secret.json"
        )

    print(f"\n{'='*80}")
    print(f"Starting OAuth authorization flow for {token_path.name}")
    print(f"Scopes: {', '.join(scopes)}")
    print(f"{'='*80}")
    print(f"A browser window will open. Please complete the authorization.")
    print(f"If the browser doesn't open, visit the URL shown below.")
    print(f"{'='*80}\n")

    try:
        # Create flow with offline access to get refresh token
        flow = InstalledAppFlow.from_client_secrets_file(
            str(CLIENT_SECRETS),
            scopes
        )
        # run_local_server automatically requests offline access (access_type=offline)
        # which ensures we get a refresh token for server use
        creds = flow.run_local_server(
            port=0,
            open_browser=True,
            authorization_prompt_message="",
            success_message="Authorization successful! You can close this window.",
        )
        
        # Verify we got a refresh token
        if not creds.refresh_token:
            print(f"\n[WARN] No refresh token received!")
            print(f"       This may happen if you've already authorized this app.")
            print(f"       For server use, you need a refresh token.")
            print(f"       Try revoking access at https://myaccount.google.com/permissions")
            print(f"       and run this script again.")
        else:
            print(f"[INFO] Refresh token received - will be saved to file")
        
        # Save the new token (creds.to_json() includes refresh_token if present)
        token_path.write_text(creds.to_json(), encoding="utf-8")
        
        # Verify refresh token was saved
        import json
        saved_data = json.loads(token_path.read_text())
        if saved_data.get("refresh_token"):
            print(f"\n[OK] New token saved to {token_path}")
            print(f"     ✓ Access token: saved")
            print(f"     ✓ Refresh token: saved (for automatic token renewal)")
        else:
            print(f"\n[WARN] Token saved but refresh_token not found in file!")
            print(f"       This token will expire and cannot be automatically renewed.")
        
        return creds
        
    except KeyboardInterrupt:
        print(f"\n[ERROR] Authorization cancelled by user")
        raise
    except AttributeError as e:
        if "'NoneType' object has no attribute 'replace'" in str(e):
            print(f"\n[ERROR] Authorization flow was interrupted or not completed.")
            print(f"       Please try again and make sure to complete the authorization in the browser.")
            print(f"       If the browser didn't open, copy the URL from above and open it manually.")
        raise
    except Exception as e:
        print(f"\n[ERROR] Authorization failed: {e}")
        print(f"       Please check your client_secret.json file and try again.")
        raise


def test_gmail(creds: Credentials) -> None:
    svc = build("gmail", "v1", credentials=creds)
    labels = svc.users().labels().list(userId="me").execute().get("labels", [])
    print(f"[OK] Gmail: {len(labels)} labels")


def test_sheets(creds: Credentials) -> None:
    svc = build("sheets", "v4", credentials=creds)
    if not SHEET_ID:
        print("[WARN] GOOGLE_SHEET_ID not set; skipping Sheets metadata check")
        return
    meta = svc.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    title = meta.get("properties", {}).get("title")
    sheet_names = [s["properties"]["title"] for s in meta.get("sheets", [])]
    print(f"[OK] Sheets: “{title}” | tabs: {', '.join(sheet_names) or '—'}")
    if WORKSHEET and WORKSHEET not in sheet_names:
        print(f"[WARN] Tab “{WORKSHEET}” not found — create/rename or change SHEET_WORKSHEET")


if __name__ == "__main__":
    if not CLIENT_SECRETS.exists():
        print(f"[ERROR] Missing client secrets file: {CLIENT_SECRETS}")
        print(f"        Please ensure GOOGLE_CLIENT_SECRETS environment variable points to client_secret.json")
        sys.exit(1)

    print(f"\n{'='*80}")
    print(f"OAuth Token Setup")
    print(f"{'='*80}")
    print(f"Client secrets: {CLIENT_SECRETS}")
    print(f"Gmail token:    {GMAIL_TOKEN}")
    print(f"Sheets token:   {SHEETS_TOKEN}")
    print(f"{'='*80}\n")

    try:
        print("Step 1/2: Authorizing Gmail access...")
        gmail_creds = ensure_token(GMAIL_TOKEN, GMAIL_SCOPES)
        print("✅ Gmail authorization complete\n")

        print("Step 2/2: Authorizing Google Sheets access...")
        sheets_creds = ensure_token(SHEETS_TOKEN, SHEETS_SCOPES)
        print("✅ Google Sheets authorization complete\n")

        # Quick sanity checks
        print("Testing credentials...")
        try:
            test_gmail(gmail_creds)
        except Exception as e:
            print(f"[WARN] Gmail test failed: {e}")

        try:
            test_sheets(sheets_creds)
        except Exception as e:
            print(f"[WARN] Sheets test failed: {e}")

        print(f"\n{'='*80}")
        print(f"✅ SUCCESS - Tokens saved:")
        print(f"   Gmail : {GMAIL_TOKEN}")
        print(f"   Sheets: {SHEETS_TOKEN}")
        print(f"{'='*80}\n")

    except KeyboardInterrupt:
        print(f"\n[ERROR] Setup cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Setup failed: {e}")
        sys.exit(1)
