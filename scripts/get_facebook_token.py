#!/usr/bin/env python3
"""
Obtains a long-lived Facebook Page access token for posting to a Page.

Page access tokens derived from a long-lived User token never expire,
so you only need to run this once (or if you revoke app access).

--- How to get a short-lived User token ---

1. Go to https://developers.facebook.com and open your photobridge app
2. In the top navigation go to Tools → Graph API Explorer
3. Make sure your photobridge app is selected in the top-right dropdown
4. Click "Generate Access Token" → choose "User Token"
5. In the permissions dialog, add all of these:
     - pages_manage_posts
     - pages_read_engagement
     - pages_show_list
6. Click "Generate Token" and log in as the Facebook account that
   manages your Page
7. Copy the token shown — it is valid for about 1 hour

--- How to get your App ID and App Secret ---

1. In the Meta Developer Console, open your photobridge app
2. Left sidebar → Settings → Basic
3. Copy the App ID and reveal/copy the App Secret

--- Token expiry ---

Long-lived Page access tokens do not expire. You only need to re-run
this script if you revoke the app's access to your Facebook account.
"""

import sys
import requests

GRAPH_API = "https://graph.facebook.com/v19.0"


def exchange_for_long_lived_user_token(app_id: str, app_secret: str, short_lived_token: str) -> str:
    resp = requests.get(
        "https://graph.facebook.com/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": short_lived_token,
        },
    )
    resp.raise_for_status()
    token = resp.json().get("access_token")
    print("  Long-lived User token obtained")
    return token


def get_page_access_token(long_lived_user_token: str) -> tuple[str, str, str]:
    """Returns (page_name, page_id, page_access_token)."""
    resp = requests.get(f"{GRAPH_API}/me/accounts", params={"access_token": long_lived_user_token})
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
        choice = input("Which page do you want to post to? Enter number: ").strip()
        page = pages[int(choice) - 1]

    return page["name"], page["id"], page["access_token"]


def main():
    print("=== photobridge Facebook token setup ===\n")
    app_id = input("Meta App ID: ").strip()
    app_secret = input("Meta App Secret: ").strip()
    short_lived_token = input("Short-lived User token (from Graph API Explorer): ").strip()

    print("\nExchanging for long-lived User token...")
    long_lived_user_token = exchange_for_long_lived_user_token(app_id, app_secret, short_lived_token)

    print("Fetching Page access token...")
    page_name, page_id, page_access_token = get_page_access_token(long_lived_user_token)
    print(f"  Found page: '{page_name}' (ID: {page_id})")

    print("\n=== Add these to your .env ===\n")
    print(f"FACEBOOK_PAGE_ID={page_id}")
    print(f"FACEBOOK_PAGE_ACCESS_TOKEN={page_access_token}")

    print("\n=== Or push directly to Secret Manager ===\n")
    print(f"  echo -n '{page_id}' | gcloud secrets versions add photobridge-fb-page-id --data-file=-")
    print(f"  echo -n '{page_access_token}' | gcloud secrets versions add photobridge-fb-page-access-token --data-file=-")

    print("\nPage access tokens derived from a long-lived User token do not expire.")
    print("You only need to re-run this script if you revoke the app's access.")


if __name__ == "__main__":
    main()
