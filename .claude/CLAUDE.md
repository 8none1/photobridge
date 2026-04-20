# photobridge — AI Assistant Context

## What this project does

photobridge is a serverless bot that bridges WhatsApp photo messages to
multiple destinations via a plugin architecture. Built-in plugins:

1. **WordPress** — uploads images to the WP Media Library via REST API
2. **Google Drive** — stores a copy in a shared folder via the Drive API
3. **Instagram** — publishes to an Instagram Business account via Graph API

Users interact by either DMing the bot's WhatsApp number or mentioning it
(@bot) in a WhatsApp group. Each plugin can be enabled/disabled independently
and optionally restricted to only fire when the photo caption contains a
specific hashtag.

## Architecture

- **Runtime**: Google Cloud Functions (2nd gen), Python 3.12
- **WhatsApp**: Meta WhatsApp Cloud API — webhook-based, no polling
- **Auth**: Service account (Drive), Application Passwords (WP), Bearer tokens (WA/Instagram)
- **Secrets**: Google Secret Manager in production; `.env` file for local dev
- **Framework**: `functions-framework` for local dev and Cloud Functions entrypoint

## Key files

| File | Purpose |
|------|---------|
| `main.py` | Cloud Function entrypoint — webhook routing, signature validation, plugin loop |
| `photobridge/config.py` | Settings loader — env vars or Secret Manager |
| `photobridge/plugins/base.py` | `BasePlugin` ABC — interface all destination plugins implement |
| `photobridge/plugins/wordpress.py` | WordPress Media Library upload (priority 10) |
| `photobridge/plugins/drive.py` | Google Drive upload (priority 10) |
| `photobridge/plugins/instagram.py` | Instagram Graph API publish (priority 20) |
| `photobridge/handlers/whatsapp.py` | WhatsApp source: download media, send replies |
| `deploy/deploy.sh` | One-shot deploy script (Secret Manager setup + gcloud deploy) |

## Plugin system

Each plugin subclasses `BasePlugin` and implements `upload()`. Plugins:
- Declare a `name` (used for config env var names and the context dict key)
- Declare a `priority` (lower runs first; Instagram=20 so WP=10 runs first)
- Read their own enable/tag config from `PLUGIN_<NAME>_*` env vars
- Receive a `context` dict with URLs from higher-priority plugins

The `context` dict is how Instagram gets a public image URL — it reads
`context['wordpress']` which the WordPress plugin populates.

To add a new plugin:
1. Create `photobridge/plugins/<name>.py` subclassing `BasePlugin`
2. Add it to the `PLUGINS` list in `main.py`
3. Add its secrets to `deploy/deploy.sh` and config vars to `.env.example`

## Plugin configuration

```
PLUGIN_<NAME>_ENABLED      true/false   (default: true)
PLUGIN_<NAME>_REQUIRE_TAG  true/false   (default: false — process all photos)
PLUGIN_<NAME>_TAG          e.g. #instagram  (default: #<name>)
```

Plugin config is passed as plain env vars (not secrets) since they hold
no credentials.

## Secrets — never commit these

All credential secrets live in Secret Manager (production) or `.env`
(local dev only). The `.env` file is gitignored. See `.env.example` for
the full list. Secret Manager secret names are all prefixed `photobridge-`.

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

## Design decisions

- **Signature validation is mandatory** — all POST requests without a valid
  `X-Hub-Signature-256` header are rejected (401). Never weaken this.
- **Always return 200 to Meta quickly** — processing is synchronous for
  simplicity; for high-volume use, fan out via Pub/Sub instead.
- **Reply failures are non-fatal** — if the confirmation message fails to
  send, the upload still counts as successful.
- **Group messages only processed when bot is @mentioned** — avoids
  processing every photo in busy groups.
- **Instagram requires WordPress** — the Instagram plugin reads the public
  URL from `context['wordpress']`. If WordPress is disabled, Instagram will
  raise a clear error. A GCS temp-URL fallback is a future extension point.
- **Plugin priority ordering** — WordPress and Drive run at priority 10;
  Instagram at 20. Lower priority = runs first.
