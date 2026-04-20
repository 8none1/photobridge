# photobridge — AI Assistant Context

## What this project does

photobridge is a serverless bot that bridges WhatsApp photo messages to:
1. **WordPress** — uploads images to the WP Media Library via REST API
2. **Google Drive** — stores a copy in a shared folder via the Drive API

Users interact by either DMing the bot's WhatsApp number or mentioning it
(@bot) in a WhatsApp group. Every image triggers an upload to both destinations,
and the bot replies with a confirmation.

## Architecture

- **Runtime**: Google Cloud Functions (2nd gen), Python 3.12
- **WhatsApp**: Meta WhatsApp Cloud API — webhook-based, no polling
- **Auth**: Service account (Drive), Application Passwords (WP), Bearer token (WA)
- **Secrets**: Google Secret Manager in production; `.env` file for local dev
- **Framework**: `functions-framework` for local dev and Cloud Functions entrypoint

## Key files

| File | Purpose |
|------|---------|
| `main.py` | Cloud Function entrypoint — webhook routing, signature validation |
| `photobridge/config.py` | Settings loader — env vars or Secret Manager |
| `photobridge/handlers/whatsapp.py` | Download media, send replies |
| `photobridge/handlers/drive.py` | Upload to Google Drive |
| `photobridge/handlers/wordpress.py` | Upload to WordPress Media Library |
| `deploy/deploy.sh` | One-shot deploy script (Secret Manager setup + gcloud deploy) |

## Secrets — never commit these

All secrets live in Secret Manager (production) or `.env` (local dev only).
The `.env` file is in `.gitignore`. See `.env.example` for the full list.

Secret Manager secret names are all prefixed `photobridge-` — see
`photobridge/config.py` for the canonical list.

## Local development

```bash
cp .env.example .env
# fill in .env values

pip install -r requirements.txt
functions-framework --target webhook --debug
# Webhook available at http://localhost:8080
# Use ngrok or similar to expose for Meta webhook testing
```

## Running tests

```bash
pip install -r requirements.txt pytest
pytest tests/
```

## Deployment

```bash
gcloud config set project YOUR_PROJECT_ID
./deploy/deploy.sh setup-secrets   # creates Secret Manager entries
# populate each secret manually (see deploy.sh output)
./deploy/deploy.sh deploy          # deploys the Cloud Function
```

## WhatsApp webhook setup (Meta Developer Console)

1. App Dashboard → WhatsApp → Configuration
2. Set Webhook URL to the Cloud Function URL
3. Set Verify Token to the value in `photobridge-wa-verify-token`
4. Subscribe to the `messages` webhook field

## Design decisions

- **Signature validation is mandatory** — all POST requests without a valid
  `X-Hub-Signature-256` header are rejected (401). Never weaken this.
- **Always return 200 to Meta quickly** — processing happens synchronously
  for simplicity; for high-volume use, fan out via Pub/Sub instead.
- **Reply failures are non-fatal** — if the confirmation message fails to
  send, the upload still counts as successful.
- **Group messages only processed when bot is @mentioned** — avoids
  processing every photo in busy groups.

## Common extension points

- **Add a Slack destination**: add `photobridge/handlers/slack.py` and call it
  alongside drive/wordpress in `main._handle_image_message()`
- **Add a gallery page**: extend `wordpress.py` to attach the uploaded media
  to a specific page ID
- **Async fan-out**: publish to a Pub/Sub topic in the webhook handler and
  process in a second function to avoid timeout risk on slow uploads
