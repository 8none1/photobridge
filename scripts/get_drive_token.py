#!/usr/bin/env python3
"""
One-time script to obtain a Google Drive OAuth refresh token.

Run this locally, complete the browser auth flow, and the refresh token
will be printed for you to store in Secret Manager (or .env for local dev).

Prerequisites:
    pip install google-auth-oauthlib

Setup:
    1. Go to Google Cloud Console → APIs & Services → Credentials
    2. Click "Create Credentials" → "OAuth client ID"
    3. Choose "Desktop app", give it a name, click Create
    4. Copy the Client ID and Client Secret when prompted below
"""

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def main():
    client_id = input("Client ID: ").strip()
    client_secret = input("Client Secret: ").strip()

    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uris": ["http://localhost"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
    )

    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")

    print("\n=== Success! Store these values in your .env and Secret Manager ===\n")
    print(f"GOOGLE_DRIVE_CLIENT_ID={client_id}")
    print(f"GOOGLE_DRIVE_CLIENT_SECRET={client_secret}")
    print(f"GOOGLE_DRIVE_REFRESH_TOKEN={creds.refresh_token}")
    print("\nTo populate Secret Manager:")
    print(f"  echo -n '{client_id}' | gcloud secrets versions add photobridge-drive-client-id --data-file=-")
    print(f"  echo -n '{client_secret}' | gcloud secrets versions add photobridge-drive-client-secret --data-file=-")
    print(f"  echo -n '{creds.refresh_token}' | gcloud secrets versions add photobridge-drive-refresh-token --data-file=-")


if __name__ == "__main__":
    main()
