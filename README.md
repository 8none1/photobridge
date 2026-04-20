# photobridge

A serverless bot that bridges WhatsApp photos to a WordPress gallery and Google Drive.

Community members post photos in a WhatsApp group (by @mentioning the bot) or send them
directly to the bot. Each image is automatically uploaded to your WordPress media library
and stored in a shared Google Drive folder.

## How it works

1. A user sends a photo to the bot via WhatsApp DM, or posts a photo in a group chat with `@photobridge`
2. Meta's WhatsApp Cloud API delivers a webhook to a Google Cloud Function
3. The function downloads the image from WhatsApp's CDN
4. The image is uploaded in parallel to:
   - **WordPress** — appears in the Media Library, ready to add to gallery pages
   - **Google Drive** — stored in a shared folder for archiving/downloading
5. The bot replies to the sender confirming the upload

## Common use cases

- **Community photo archives** — WhatsApp groups that share event photos, allowing everyone to contribute to a shared gallery without needing login credentials to any system
- **Club or society websites** — members send match-day or event photos straight to the club site
- **Family groups** — relatives share photos that automatically appear in a family WordPress album and a shared Google Drive

## Prerequisites

- A **Meta Business Account** and a WhatsApp Business phone number
- A **WordPress site** with the REST API enabled (default on WP 5.6+)
- A **Google Cloud project** (free tier is sufficient)
- A **Google Drive folder** shared with a service account

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_ORG/photobridge.git
cd photobridge
```

### 2. Configure secrets

Never commit real secrets. All credentials are managed via Google Secret Manager
in production or a local `.env` file for development.

```bash
cp .env.example .env
# Edit .env — fill in all values
```

See `.env.example` for the full list of required values and where to find each one.

### 3. Set up WhatsApp

1. Create a Meta Developer App at [developers.facebook.com](https://developers.facebook.com)
2. Add the **WhatsApp** product
3. Register or link a phone number
4. Generate a permanent access token
5. Copy the Phone Number ID and App Secret — you'll need both

### 4. Set up WordPress

1. In WordPress Admin: **Users → Profile → Application Passwords**
2. Create a new Application Password named "photobridge"
3. Copy the generated password (shown only once)

### 5. Set up Google Drive

1. Create a GCP project and enable the Drive API
2. Create a Service Account and download the JSON key
3. Share your target Drive folder with the service account's email address (Editor access)

### 6. Deploy

```bash
gcloud config set project YOUR_PROJECT_ID

# Create Secret Manager entries
./deploy/deploy.sh setup-secrets

# Populate each secret (output from the previous step shows the commands)
echo -n 'YOUR_VALUE' | gcloud secrets versions add photobridge-wa-access-token --data-file=-
# ... repeat for all secrets

# Deploy the Cloud Function
./deploy/deploy.sh deploy
```

### 7. Register the webhook

1. In the Meta Developer Console: **App Dashboard → WhatsApp → Configuration**
2. Set **Webhook URL** to the Cloud Function URL printed by the deploy script
3. Set **Verify Token** to the value you stored in `photobridge-wa-verify-token`
4. Subscribe to the **messages** webhook field

### 8. Add the bot to your WhatsApp group

Add the WhatsApp Business number to your community group. Members can then
either DM the number or mention it in the group to trigger an upload.

## Local development

```bash
pip install -r requirements.txt
functions-framework --target webhook --debug
# Webhook available at http://localhost:8080
```

To test with real WhatsApp webhooks locally, expose your local server:

```bash
ngrok http 8080
# Use the ngrok HTTPS URL as the webhook URL in Meta Developer Console
```

## Running tests

```bash
pip install -r requirements.txt pytest
pytest tests/
```

## Security notes

- All incoming webhook POST requests are validated against the `X-Hub-Signature-256`
  header using your Meta App Secret. Requests without a valid signature are rejected.
- Secrets are never read from the source code. Use `.env` locally, Secret Manager in production.
- The `.env` file and all credential JSON files are gitignored — double-check before committing.

## Architecture

See [docs/design.md](docs/design.md) for the full design document including architecture
diagrams and component breakdown.

## License

See [LICENSE](LICENSE).
