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
  "photobridge-drive-client-id"
  "photobridge-drive-client-secret"
  "photobridge-drive-refresh-token"
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

# Read a variable's value from a .env file; returns empty if missing or still a placeholder.
get_env_val() {
  local var="$1"
  local val
  val=$(grep -E "^${var}=" .env 2>/dev/null | head -1 | cut -d= -f2-)
  if [[ -z "$val" || "$val" == *"_here" || "$val" =~ ^your_ ]]; then
    echo ""
  else
    echo "$val"
  fi
}

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
    fi
  done

  if [[ ! -f ".env" ]]; then
    echo ""
    echo "No .env file found — populate each secret manually:"
    for secret in "${SECRET_NAMES[@]}"; do
      echo "  echo -n 'VALUE' | gcloud secrets versions add $secret --data-file=-"
    done
    echo ""
    echo "After populating all secrets, run:  ./deploy/deploy.sh deploy"
    return
  fi

  echo ""
  echo "=== Populating secrets from .env ==="

  local unpopulated=()

  # env var name → secret manager name
  local -a pairs=(
    "WHATSAPP_PHONE_NUMBER_ID:photobridge-wa-phone-number-id"
    "WHATSAPP_ACCESS_TOKEN:photobridge-wa-access-token"
    "WHATSAPP_VERIFY_TOKEN:photobridge-wa-verify-token"
    "WHATSAPP_APP_SECRET:photobridge-wa-app-secret"
    "WORDPRESS_URL:photobridge-wp-url"
    "WORDPRESS_USERNAME:photobridge-wp-username"
    "WORDPRESS_APP_PASSWORD:photobridge-wp-app-password"
    "GOOGLE_DRIVE_FOLDER_ID:photobridge-drive-folder-id"
    "GOOGLE_DRIVE_CLIENT_ID:photobridge-drive-client-id"
    "GOOGLE_DRIVE_CLIENT_SECRET:photobridge-drive-client-secret"
    "GOOGLE_DRIVE_REFRESH_TOKEN:photobridge-drive-refresh-token"
    "INSTAGRAM_USER_ID:photobridge-instagram-user-id"
    "INSTAGRAM_ACCESS_TOKEN:photobridge-instagram-access-token"
  )

  for pair in "${pairs[@]}"; do
    local env_var="${pair%%:*}"
    local secret="${pair##*:}"
    local val
    val=$(get_env_val "$env_var")
    if [[ -n "$val" ]]; then
      echo -n "$val" | gcloud secrets versions add "$secret" \
        --project="$PROJECT_ID" --data-file=-
      echo "  [populated] $secret"
    else
      unpopulated+=("$secret  ← $env_var")
    fi
  done

  if [[ ${#unpopulated[@]} -gt 0 ]]; then
    echo ""
    echo "These secrets were not populated (missing, placeholder, or file not found in .env):"
    for item in "${unpopulated[@]}"; do
      echo "  $item"
    done
    echo ""
    echo "Set them manually with:"
    echo "  echo -n 'VALUE' | gcloud secrets versions add SECRET_NAME --data-file=-"
  fi

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

  echo "=== Granting Secret Manager access to the Cloud Function ==="
  local project_number
  project_number=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${project_number}-compute@developer.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor" \
    --condition=None \
    --quiet

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
