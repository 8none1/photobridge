#!/usr/bin/env bash
# deploy/deploy.sh
#
# Deploys photobridge to Google Cloud Functions (2nd gen).
# Run once to set up Secret Manager entries, then again to deploy the function.
#
# Prerequisites:
#   gcloud CLI installed and authenticated
#   gcloud config set project YOUR_PROJECT_ID
#
# Usage:
#   ./deploy/deploy.sh [setup-secrets|deploy|all]
#
set -euo pipefail

PROJECT_ID=$(gcloud config get-value project)
REGION="us-central1"
FUNCTION_NAME="photobridge"
RUNTIME="python312"
SOURCE_DIR="."

# Names of secrets in Secret Manager (must match photobridge/config.py)
SECRET_NAMES=(
  # WhatsApp
  "photobridge-wa-phone-number-id"
  "photobridge-wa-access-token"
  "photobridge-wa-verify-token"
  "photobridge-wa-app-secret"
  # WordPress
  "photobridge-wp-url"
  "photobridge-wp-username"
  "photobridge-wp-app-password"
  # Google Drive
  "photobridge-drive-folder-id"
  "photobridge-service-account-json"
  # Instagram
  "photobridge-instagram-user-id"
  "photobridge-instagram-access-token"
)

# Plugin on/off and tag configuration is set via plain env vars (not secrets)
# because they contain no credentials. Adjust these defaults as needed.
PLUGIN_ENV_VARS=(
  "PLUGIN_WORDPRESS_ENABLED=true"
  "PLUGIN_WORDPRESS_REQUIRE_TAG=false"
  "PLUGIN_WORDPRESS_TAG=#wordpress"
  "PLUGIN_DRIVE_ENABLED=true"
  "PLUGIN_DRIVE_REQUIRE_TAG=false"
  "PLUGIN_DRIVE_TAG=#drive"
  "PLUGIN_INSTAGRAM_ENABLED=true"
  "PLUGIN_INSTAGRAM_REQUIRE_TAG=false"
  "PLUGIN_INSTAGRAM_TAG=#instagram"
)

function setup_secrets() {
  echo "=== Creating Secret Manager secrets ==="
  for secret in "${SECRET_NAMES[@]}"; do
    if gcloud secrets describe "$secret" --project="$PROJECT_ID" &>/dev/null; then
      echo "  [exists] $secret"
    else
      gcloud secrets create "$secret" \
        --project="$PROJECT_ID" \
        --replication-policy="automatic"
      echo "  [created] $secret"
      echo "  --> Set its value with:"
      echo "      echo -n 'YOUR_VALUE' | gcloud secrets versions add $secret --data-file=-"
    fi
  done

  echo ""
  echo "After populating all secrets, run:  ./deploy/deploy.sh deploy"
}

function deploy_function() {
  echo "=== Enabling required APIs ==="
  gcloud services enable \
    cloudfunctions.googleapis.com \
    run.googleapis.com \
    secretmanager.googleapis.com \
    drive.googleapis.com \
    --project="$PROJECT_ID"

  # Build the --set-env-vars string from PLUGIN_ENV_VARS array
  PLUGIN_VARS_CSV=$(IFS=,; echo "${PLUGIN_ENV_VARS[*]}")

  echo "=== Deploying Cloud Function ==="
  gcloud functions deploy "$FUNCTION_NAME" \
    --gen2 \
    --runtime="$RUNTIME" \
    --region="$REGION" \
    --source="$SOURCE_DIR" \
    --entry-point="webhook" \
    --trigger-http \
    --allow-unauthenticated \
    --set-env-vars="USE_SECRET_MANAGER=true,GCP_PROJECT_ID=${PROJECT_ID},${PLUGIN_VARS_CSV}" \
    --project="$PROJECT_ID"

  FUNCTION_URL=$(gcloud functions describe "$FUNCTION_NAME" \
    --gen2 \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --format="value(serviceConfig.uri)")

  echo ""
  echo "=== Deployment complete ==="
  echo "Webhook URL: ${FUNCTION_URL}"
  echo ""
  echo "Register this URL in the Meta Developer Console:"
  echo "  App Dashboard → WhatsApp → Configuration → Webhook URL"
  echo "  Verify Token: (the value stored in photobridge-wa-verify-token)"
  echo "  Subscribe to: messages"
}

case "${1:-all}" in
  setup-secrets) setup_secrets ;;
  deploy)        deploy_function ;;
  all)           setup_secrets && deploy_function ;;
  *)             echo "Usage: $0 [setup-secrets|deploy|all]"; exit 1 ;;
esac
