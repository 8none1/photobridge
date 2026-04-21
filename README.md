# photobridge

A serverless bot that bridges WhatsApp photos to a WordPress gallery, Google Drive, and Instagram.

Community members post photos in a WhatsApp group (by @mentioning the bot) or send them
directly to the bot. Each image is automatically uploaded to your configured destinations.
New destinations can be added as plugins with no changes to the core code.

## How it works

1. A user sends a photo to the bot via WhatsApp DM, or posts a photo in a group chat with `@photobridge`
2. Meta's WhatsApp Cloud API delivers a webhook to a Google Cloud Function
3. The function downloads the image from WhatsApp's CDN
4. The image is passed through all enabled destination plugins in order:
   - **WordPress** — uploaded to the Media Library, ready to add to gallery pages
   - **Google Drive** — stored in a shared folder for archiving and downloading
   - **Instagram** — published to an Instagram Business account (uses the WordPress public URL)
5. The bot replies to the sender confirming which destinations received the photo

## Destination plugins

Each destination can be independently enabled or disabled. You can also require a specific
hashtag in the caption before a destination fires — useful for keeping Instagram opt-in
while everything else is automatic.

| Plugin | Default | Trigger tag |
|--------|---------|-------------|
| WordPress | Always on | `#wordpress` (if tag mode enabled) |
| Google Drive | Always on | `#drive` (if tag mode enabled) |
| Instagram | Always on | `#instagram` (if tag mode enabled) |

To make Instagram opt-in rather than automatic, set `PLUGIN_INSTAGRAM_REQUIRE_TAG=true`
in your environment. A photo captioned "Great day out! #instagram" will then be posted
to Instagram; one without the tag will not.

## Common use cases

- **Community photo archives** — WhatsApp groups that share event photos, letting everyone
  contribute to a shared gallery without needing login credentials to any system
- **Club or society websites** — members send match-day or event photos straight to the club site
- **Family groups** — relatives share photos that automatically appear in a family WordPress album
  and a shared Google Drive folder

---

## Setup

### Prerequisites

- A **Google account** with access to Google Cloud (free tier is sufficient)
- A **Meta Business account** and a dedicated phone number for the bot
- A **WordPress site** (self-hosted or managed, WP 5.6+)
- Optionally: an **Instagram Business or Creator account** linked to a Facebook Page

---

### Step 1 — Clone the repo

```bash
git clone https://github.com/YOUR_ORG/photobridge.git
cd photobridge
cp .env.example .env
```

Fill in `.env` as you work through the steps below. Never commit this file.

---

### Step 2 — Google Cloud project

#### 2a. Create a project

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Click the project dropdown at the top → **New Project**
3. Give it a name (e.g. `photobridge`) and click **Create**
4. Note the **Project ID** — you'll need it throughout

#### 2b. Enable billing

Cloud Functions (2nd gen) requires billing to be enabled even though usage
stays well within the free tier for a community bot.

1. In the Cloud Console: **Billing** → **Link a billing account**
2. Add a payment method if you don't have one

> The free tier covers 2 million function invocations and 400,000 GB-seconds
> of compute per month — far more than needed for a community photo bot.

#### 2c. Enable required APIs

Run these once, or let `deploy.sh` do it automatically:

```bash
gcloud config set project YOUR_PROJECT_ID

gcloud services enable \
  cloudfunctions.googleapis.com \
  run.googleapis.com \
  secretmanager.googleapis.com \
  drive.googleapis.com
```

---

### Step 3 — Google Drive

photobridge uses OAuth user credentials to upload to Drive, so files are owned
by your Google account and count against your personal storage quota.

#### 3a. Create an OAuth client

1. Go to [Google Cloud Console](https://console.cloud.google.com) → **APIs & Services → Credentials**
2. Click **Create Credentials → OAuth client ID**
3. If prompted to configure the consent screen: choose **External**, fill in an
   app name (e.g. `photobridge`), add your Google account as a test user, and save
4. Application type: **Desktop app** — give it a name and click **Create**
5. Note the **Client ID** and **Client Secret**

Set them in your `.env`:
```
GOOGLE_DRIVE_CLIENT_ID=your_client_id
GOOGLE_DRIVE_CLIENT_SECRET=your_client_secret
```

#### 3b. Generate a refresh token

Run the helper script once locally:

```bash
pip install google-auth-oauthlib
python scripts/get_drive_token.py
```

A browser window will open asking you to sign in with your Google account and
grant Drive access. Once complete, the script prints your refresh token and the
exact `gcloud` commands to store it in Secret Manager.

Set in your `.env`:
```
GOOGLE_DRIVE_REFRESH_TOKEN=your_refresh_token
```

#### 3c. Create a Drive folder

1. Go to [drive.google.com](https://drive.google.com) and create a folder
   (e.g. "photobridge uploads")
2. Click the folder, look at the URL: `https://drive.google.com/drive/folders/FOLDER_ID`
3. Copy the `FOLDER_ID` and set `GOOGLE_DRIVE_FOLDER_ID=FOLDER_ID` in your `.env`

No sharing or service account setup required — the function uploads as you.

---

### Step 4 — WordPress

#### 4a. Generate an Application Password

Application Passwords (WP 5.6+) let photobridge authenticate to the REST API
without using your main account password.

1. Log in to WordPress Admin
2. Go to **Users → Profile** (or **Users → All Users** → edit the account you want the bot to use)
3. Scroll down to **Application Passwords**
4. Enter a name (e.g. `photobridge`) and click **Add New Application Password**
5. Copy the generated password immediately — it is only shown once

Set these in your `.env`:
```
WORDPRESS_URL=https://your-site.com
WORDPRESS_USERNAME=the_wp_username
WORDPRESS_APP_PASSWORD=xxxx xxxx xxxx xxxx xxxx xxxx
```

#### 4b. Verify the REST API is reachable

```bash
curl https://your-site.com/wp-json/wp/v2/media \
  --user "your_username:xxxx xxxx xxxx xxxx xxxx xxxx"
# Should return a JSON array (possibly empty), not a 404 or auth error
```

If your host blocks the REST API, check **Settings → Permalinks** (resaving
often fixes it) or contact your hosting provider.

---

### Step 5 — WhatsApp Cloud API (Meta)

#### 5a. Create a Meta Developer App

1. Go to [developers.facebook.com](https://developers.facebook.com) and log in
   with your Meta Business account
2. Click **My Apps → Create App**
3. Select **Business** as the app type
4. Give it a name (e.g. `photobridge`) and click **Create App**

#### 5b. Add the WhatsApp product

1. In your app dashboard, find **WhatsApp** and click **Set up**
2. You'll land on the WhatsApp **Getting Started** page
3. Meta provides a free test phone number — use this while developing

#### 5c. Collect credentials

From the **Getting Started** page:
- **Phone Number ID** — shown under "From" in the test number section
- **Temporary access token** — shown in the curl example (valid 24h for testing)

From **App Settings → Basic**:
- **App Secret** — click the eye icon to reveal it

For production you'll want a **permanent System User token**:
1. Go to [business.facebook.com](https://business.facebook.com) → **Settings → System Users**
2. Create a System User with **Employee** role
3. Click **Add Assets**, assign your WhatsApp app with **Full control**
4. Click **Generate Token**, select your app, enable `whatsapp_business_messaging`
5. Copy the token — this is your permanent `WHATSAPP_ACCESS_TOKEN`

Set these in your `.env`:
```
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id
WHATSAPP_ACCESS_TOKEN=your_token
WHATSAPP_APP_SECRET=your_app_secret
WHATSAPP_VERIFY_TOKEN=choose_any_random_string
```

The verify token is something you make up — photobridge uses it to confirm
to Meta that the webhook endpoint belongs to you.

#### 5d. Add a real phone number (production)

1. In the WhatsApp product: **Phone Numbers → Add phone number**
2. Enter a number you own (mobile or VoIP — must be able to receive an SMS or call)
3. Complete the verification

---

### Step 6 — Instagram (optional)

Skip this step if you don't need Instagram publishing.

#### 6a. Requirements

- An **Instagram Business or Creator** account (personal accounts cannot publish via API)
- The Instagram account must be **linked to a Facebook Page**
  - Instagram app → Settings → Account → Linked Accounts → Facebook

#### 6b. Add Instagram to your Meta App

1. In your Meta Developer App dashboard → **Add Product → Instagram**
2. Go to **Instagram → Basic Display** and add your Instagram account as a test user
3. Go to **Instagram → Graph API** → generate a token with these permissions:
   - `instagram_basic`
   - `instagram_content_publish`

For production use a **long-lived token** (60-day expiry, renewable):
```bash
curl -i -X GET "https://graph.facebook.com/oauth/access_token \
  ?grant_type=fb_exchange_token \
  &client_id=YOUR_APP_ID \
  &client_secret=YOUR_APP_SECRET \
  &fb_exchange_token=YOUR_SHORT_LIVED_TOKEN"
```

#### 6c. Find your Instagram User ID

```bash
curl "https://graph.facebook.com/v19.0/me/accounts \
  ?access_token=YOUR_LONG_LIVED_TOKEN"
# Find the page, then:
curl "https://graph.facebook.com/v19.0/YOUR_PAGE_ID \
  ?fields=instagram_business_account \
  &access_token=YOUR_LONG_LIVED_TOKEN"
```

The `instagram_business_account.id` value is your `INSTAGRAM_USER_ID`.

Set these in your `.env`:
```
INSTAGRAM_USER_ID=your_instagram_user_id
INSTAGRAM_ACCESS_TOKEN=your_long_lived_token
```

---

### Step 7 — Deploy to Google Cloud

#### 7a. Set up Secret Manager

Make sure your `.env` is fully populated (all values from the earlier steps),
then run from the **repo root**:

```bash
gcloud config set project YOUR_PROJECT_ID
./deploy/deploy.sh setup-secrets
```

This creates all required secrets in Secret Manager **and populates them from
your `.env` file** in one step. The service account JSON is read from the path
set in `GOOGLE_SERVICE_ACCOUNT_KEY_PATH` and its contents are stored as the secret.

If any values are missing or still contain placeholder text, the script will
list them and show the manual command to set each one:

```bash
echo -n 'VALUE' | gcloud secrets versions add SECRET_NAME --data-file=-
```

Re-running `setup-secrets` after updating `.env` is safe — it adds a new secret
version (promoting it to latest) without touching other secrets.

#### 7b. Deploy the function

```bash
./deploy/deploy.sh deploy
```

This enables the required APIs, grants the Cloud Function's service account
access to Secret Manager, and deploys the function. It will print a
**Webhook URL** when it finishes. Keep it handy for the next step.

To override the default plugin settings at deploy time, edit the `PLUGIN_ENV_VARS`
array near the top of `deploy/deploy.sh` before running.

---

### Step 8 — Register the webhook with Meta

1. In your Meta Developer App: **WhatsApp → Configuration**
2. Under **Webhook**, click **Edit**
3. Set **Callback URL** to the Cloud Function URL from step 7c
4. Set **Verify Token** to the same value you stored in `photobridge-wa-verify-token`
5. Click **Verify and Save** — Meta will send a GET request to your function to confirm it responds correctly
6. Under **Webhook fields**, click **Manage** and subscribe to **messages**

---

### Step 9 — Add the bot to your WhatsApp group

1. Open WhatsApp and start a new chat with the bot's phone number to confirm it's live
2. Send a test photo — you should receive a confirmation reply
3. Add the bot's number to your community group as a participant
4. Members can now @mention the bot when posting a photo to trigger an upload

---

## Local development

```bash
pip install -r requirements.txt
functions-framework --target webhook --debug
# Webhook available at http://localhost:8080
```

To test with real WhatsApp webhooks locally, expose your local server using
[ngrok](https://ngrok.com) or a similar tunnel:

```bash
ngrok http 8080
# Register the ngrok HTTPS URL as the webhook in the Meta Developer Console
```

You can also send test events directly:

```bash
# Simulate a webhook verification handshake
curl "http://localhost:8080/?hub.mode=subscribe&hub.verify_token=YOUR_VERIFY_TOKEN&hub.challenge=test123"

# Simulate an incoming image message (replace APP_SECRET with your value)
BODY='{"entry":[{"changes":[{"value":{"messages":[{"type":"image","from":"447700900000","image":{"id":"test-media-id","caption":"test"}}]}}]}]}'
SIG=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "YOUR_APP_SECRET" | awk '{print "sha256="$2}')
curl -X POST http://localhost:8080/ \
  -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: $SIG" \
  -d "$BODY"
```

---

## Running tests

```bash
pip install -r requirements.txt pytest
pytest tests/ -v
```

---

## Plugin configuration reference

> **Important:** any plugin that is enabled but missing credentials will cause
> a 500 error on every incoming photo. If you haven't set up Instagram yet,
> set `PLUGIN_INSTAGRAM_ENABLED=false` before deploying.

All plugin settings are plain environment variables (not secrets).

| Variable | Default | Description |
|----------|---------|-------------|
| `PLUGIN_WORDPRESS_ENABLED` | `true` | Enable/disable WordPress uploads |
| `PLUGIN_WORDPRESS_REQUIRE_TAG` | `false` | Only upload if caption contains the tag |
| `PLUGIN_WORDPRESS_TAG` | `#wordpress` | Tag to require when `REQUIRE_TAG=true` |
| `PLUGIN_DRIVE_ENABLED` | `true` | Enable/disable Google Drive uploads |
| `PLUGIN_DRIVE_REQUIRE_TAG` | `false` | Only upload if caption contains the tag |
| `PLUGIN_DRIVE_TAG` | `#drive` | Tag to require when `REQUIRE_TAG=true` |
| `PLUGIN_INSTAGRAM_ENABLED` | `true` | Enable/disable Instagram publishing |
| `PLUGIN_INSTAGRAM_REQUIRE_TAG` | `false` | Only post if caption contains the tag |
| `PLUGIN_INSTAGRAM_TAG` | `#instagram` | Tag to require when `REQUIRE_TAG=true` |

**Example: make Instagram opt-in**

In `deploy/deploy.sh`, change:
```bash
"PLUGIN_INSTAGRAM_REQUIRE_TAG=false"
```
to:
```bash
"PLUGIN_INSTAGRAM_REQUIRE_TAG=true"
```
Then redeploy. Photos will only reach Instagram when the sender includes `#instagram` in the caption.

---

## Security notes

- All incoming webhook POST requests are validated against the `X-Hub-Signature-256`
  header using your Meta App Secret. Requests without a valid signature are rejected with 401.
- Secrets are never stored in source code. Use `.env` locally, Secret Manager in production.
- The `.env` file and all service account JSON files are gitignored — verify with
  `git status` before committing.
- Instagram long-lived tokens expire after 60 days. Set a calendar reminder to refresh
  the token before expiry using the exchange endpoint in step 6b.

## Architecture

See [docs/design.md](docs/design.md) for the full design document with architecture
diagrams and component breakdown.

## License

See [LICENSE](LICENSE).
