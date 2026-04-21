#!/usr/bin/env python3
"""
Exchanges a short-lived Meta User token for a long-lived one and
retrieves the Instagram Business/Creator User ID.

Usage:
    python scripts/get_instagram_token.py

--- How to get a short-lived User token ---

1. Go to https://developers.facebook.com and open your photobridge app
2. In the top navigation go to Tools → Graph API Explorer
3. In the top-right dropdown, make sure your photobridge app is selected
4. Click "Generate Access Token" → choose "User Token"
5. In the permissions dialog, add all of these:
     - instagram_basic
     - instagram_content_publish
     - pages_show_list
     - pages_read_engagement
6. Click "Generate Token" and log in as the Facebook account that
   manages the Page linked to your Instagram account
7. Copy the token shown — it is valid for about 1 hour

--- How to get your App ID and App Secret ---

1. In the Meta Developer Console, open your photobridge app
2. Left sidebar → Settings → Basic
3. Copy the App ID and reveal/copy the App Secret

--- Token expiry ---

The long-lived token this script produces expires after ~60 days.
Re-run this script with a fresh short-lived token to rotate it, then
run ./deploy/deploy.sh setup-secrets and redeploy.
"""

import sys
import requests


GRAPH_API = "https://graph.facebook.com/v19.0"


def exchange_token(app_id: str, app_secret: str, short_lived_token: str) -> str:
    resp = requests.get(
        f"https://graph.facebook.com/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": short_lived_token,
        },
    )
    resp.raise_for_status()
    data = resp.json()
    token = data.get("access_token")
    expires_in = data.get("expires_in", 0)
    days = expires_in // 86400
    print(f"  Long-lived token obtained (expires in ~{days} days)")
    return token


def get_instagram_user_id(long_lived_token: str) -> tuple[str, str]:
    """Returns (page_name, instagram_user_id)."""
    resp = requests.get(f"{GRAPH_API}/me/accounts", params={"access_token": long_lived_token})
    resp.raise_for_status()
    pages = resp.json().get("data", [])

    if not pages:
        print("ERROR: No Facebook Pages found for this account.")
        sys.exit(1)

    if len(pages) == 1:
        page = pages[0]
    else:
        print("\nMultiple Facebook Pages found:")
        for i, p in enumerate(pages):
            print(f"  {i + 1}. {p['name']} (ID: {p['id']})")
        choice = input("Which page is linked to your Instagram? Enter number: ").strip()
        page = pages[int(choice) - 1]

    page_id = page["id"]
    page_name = page["name"]

    resp = requests.get(
        f"{GRAPH_API}/{page_id}",
        params={"fields": "instagram_business_account", "access_token": long_lived_token},
    )
    resp.raise_for_status()
    ig = resp.json().get("instagram_business_account")

    if not ig:
        print(f"ERROR: No Instagram account linked to page '{page_name}'.")
        print("Make sure your Instagram Creator/Business account is linked to this Page.")
        sys.exit(1)

    return page_name, ig["id"]


def main():
    print("=== photobridge Instagram token setup ===\n")
    app_id = input("Meta App ID: ").strip()
    app_secret = input("Meta App Secret: ").strip()
    short_lived_token = input("Short-lived User token (from Graph API Explorer): ").strip()

    print("\nExchanging for long-lived token...")
    long_lived_token = exchange_token(app_id, app_secret, short_lived_token)

    print("Finding Instagram User ID...")
    page_name, instagram_user_id = get_instagram_user_id(long_lived_token)
    print(f"  Found Instagram account linked to '{page_name}'")

    print("\n=== Add these to your .env ===\n")
    print(f"INSTAGRAM_USER_ID={instagram_user_id}")
    print(f"INSTAGRAM_ACCESS_TOKEN={long_lived_token}")

    print("\n=== Or push directly to Secret Manager ===\n")
    print(f"  echo -n '{instagram_user_id}' | gcloud secrets versions add photobridge-instagram-user-id --data-file=-")
    print(f"  echo -n '{long_lived_token}' | gcloud secrets versions add photobridge-instagram-access-token --data-file=-")

    print("\nRemember to refresh this token before it expires (~60 days).")
    print("Re-run this script with a new short-lived token to rotate it.")


if __name__ == "__main__":
    main()
