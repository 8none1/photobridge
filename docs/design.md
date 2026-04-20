# photobridge — Design Document

## Overview

photobridge is a serverless bot that lets members of a WhatsApp community share
photos directly to a shared WordPress gallery and Google Drive folder. Users send
a photo to the bot via DM, or post it in a WhatsApp group with an @mention. The
bot handles the rest with no manual moderation step.

---

## Goals

- Zero infrastructure to maintain (serverless, managed services only)
- Free or near-free to run for community-scale usage (~hundreds of photos/month)
- Secrets never stored in source control
- Easy to extend with additional upload destinations

## Non-Goals

- Video support (WhatsApp compresses video; out of scope for v1)
- Image moderation or content filtering
- Multi-tenant support (single community, single WP site, single Drive folder)

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  WhatsApp (user device)                                             │
│                                                                     │
│  User sends photo  ──► Group chat (@photobridge)                    │
│                    ──► DM to bot number                             │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  HTTPS webhook (POST)
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Meta WhatsApp Cloud API                                            │
│                                                                     │
│  • Validates & buffers the message                                  │
│  • Stores media temporarily (accessible via media ID)              │
│  • Delivers webhook to configured URL                               │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  HTTPS webhook (POST)
                               │  X-Hub-Signature-256 header
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Google Cloud Function (photobridge)                                │
│                                                                     │
│  main.py                                                            │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  webhook()                                                    │  │
│  │  ├── GET  → webhook verification handshake                   │  │
│  │  └── POST → validate signature                               │  │
│  │             parse payload                                    │  │
│  │             for each image message:                          │  │
│  │               ├── WhatsAppHandler.download_media()           │  │
│  │               ├── DriveHandler.upload()          ──────────► │──┼──► Google Drive
│  │               ├── WordPressHandler.upload()      ──────────► │──┼──► WordPress
│  │               └── WhatsAppHandler.send_reply()              │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  photobridge/config.py                                              │
│  └── reads from Secret Manager (prod) or .env (local dev)          │
└─────────────────────────────────────────────────────────────────────┘
                    │                           │
                    ▼                           ▼
        ┌───────────────────┐       ┌────────────────────┐
        │  Google Drive     │       │  WordPress         │
        │                   │       │                    │
        │  Shared folder    │       │  Media Library     │
        │  (service account │       │  (REST API +       │
        │   write access)   │       │   App Password)    │
        └───────────────────┘       └────────────────────┘
                    ▲
                    │
        ┌───────────────────┐
        │  Secret Manager   │
        │                   │
        │  All credentials  │
        │  at runtime       │
        └───────────────────┘
```

---

## Message Flow

```
User                  Meta API          Cloud Function       Drive / WP
 │                       │                    │                  │
 │── Send photo ─────────►│                    │                  │
 │   (group @mention      │                    │                  │
 │    or DM)              │                    │                  │
 │                        │── POST webhook ───►│                  │
 │                        │   (image message)  │                  │
 │                        │                    │── GET media ────►│ (Meta CDN)
 │                        │                    │◄─ image bytes ───│
 │                        │                    │                  │
 │                        │                    │── upload ────────────────────►│ Drive
 │                        │                    │◄─ Drive URL ─────────────────│
 │                        │                    │                  │
 │                        │                    │── POST media ────────────────►│ WP
 │                        │                    │◄─ media URL ─────────────────│
 │                        │                    │                  │
 │                        │◄── 200 OK ─────────│                  │
 │                        │                    │                  │
 │◄── "Photo uploaded!" ──│◄── send_reply ─────│                  │
```

---

## Component Breakdown

### `main.py` — Entrypoint

- Handles the Meta webhook verification GET request
- Validates `X-Hub-Signature-256` on all POST requests (HMAC-SHA256)
- Walks the webhook payload structure to find image messages
- Filters group messages to only those @mentioning the bot
- Calls handlers in sequence; reply failures are non-fatal

### `photobridge/config.py` — Settings

- In production (`USE_SECRET_MANAGER=true`): fetches secrets from Google
  Secret Manager using the runtime service account's IAM permissions
- In local dev: loads from `.env` via `python-dotenv`
- Secret names are all prefixed `photobridge-` to namespace them in GCP

### `photobridge/handlers/whatsapp.py`

- `download_media(media_id)`: Two-step fetch — resolve URL, then download
  bytes. Meta requires the same Bearer token for both requests.
- `send_reply(recipient, text)`: Plain-text message back to sender.
  Non-fatal: logged and swallowed if it fails.

### `photobridge/handlers/drive.py`

- Authenticates via service account credentials (`google-auth` library)
- Uploads with `MediaIoBaseUpload` (non-resumable for images up to ~5MB)
- Returns the `webViewLink` for logging

### `photobridge/handlers/wordpress.py`

- POSTs raw image bytes to `/wp-json/wp/v2/media`
- Uses HTTP Basic Auth with an Application Password (not the account password)
- Optionally updates the `caption` field in a follow-up PATCH

---

## Secrets Management

| Secret name | What it holds |
|---|---|
| `photobridge-wa-phone-number-id` | WhatsApp Business phone number ID |
| `photobridge-wa-access-token` | Meta permanent access token |
| `photobridge-wa-verify-token` | Self-chosen token for webhook verification |
| `photobridge-wa-app-secret` | Meta app secret (for signature validation) |
| `photobridge-wp-url` | WordPress site URL |
| `photobridge-wp-username` | WordPress username |
| `photobridge-wp-app-password` | WordPress Application Password |
| `photobridge-drive-folder-id` | Google Drive target folder ID |
| `photobridge-service-account-json` | Full service account JSON key |

In production all of these are stored in **Google Secret Manager** and accessed
at runtime. The Cloud Function's service account is granted
`roles/secretmanager.secretAccessor` on each secret.

For local development, copy `.env.example` to `.env` and fill in real values.
The `.env` file is gitignored and should never be committed.

---

## Infrastructure

All infrastructure is Google Cloud, free-tier:

| Service | Usage | Free tier |
|---|---|---|
| Cloud Functions (2nd gen) | Webhook receiver | 2M req/month, 400K GB-sec |
| Secret Manager | Credentials at runtime | 6 active versions, 10K ops/month |
| Google Drive API | Photo storage | Storage within Drive quota |

WhatsApp Cloud API is free up to 1,000 user-initiated conversations/month
(a "conversation" = 24-hour window, not per-message).

---

## Deployment

See `deploy/deploy.sh` for the full script. The high-level steps are:

1. Create a GCP project and enable billing (required even for free tier)
2. Run `./deploy/deploy.sh setup-secrets` to create Secret Manager entries
3. Populate each secret with its value (done once, out-of-band)
4. Run `./deploy/deploy.sh deploy` to deploy the Cloud Function
5. Register the Cloud Function URL as a WhatsApp webhook in the Meta Developer Console

---

## Local Development

```bash
cp .env.example .env
# edit .env with real values

pip install -r requirements.txt
functions-framework --target webhook --debug
# → http://localhost:8080

# Expose to the internet for Meta webhook testing:
ngrok http 8080
# Use the ngrok HTTPS URL in the Meta Developer Console
```

---

## Future Considerations

- **Pub/Sub fan-out**: Move upload tasks to a Pub/Sub queue for resilience and
  to keep webhook response times under Meta's timeout.
- **Duplicate detection**: Hash incoming images and skip re-uploads.
- **Gallery page attachment**: Extend WordPress handler to attach uploaded media
  to a dedicated gallery page automatically.
- **Additional sources**: Signal, Telegram, or email attachments could feed the
  same handler pipeline with new source adapters.
- **Moderation**: A lightweight Cloud Vision API call could flag inappropriate
  images before upload.
