"""
Configuration loader.

In local development, reads from a .env file (or environment variables).
In production (Cloud Run / Cloud Functions), reads secrets from
Google Secret Manager when USE_SECRET_MANAGER=true.
"""

import json
import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    def __init__(self):
        self._use_secret_manager = os.getenv("USE_SECRET_MANAGER", "false").lower() == "true"
        self._project_id = os.getenv("GCP_PROJECT_ID", "")

    def _get(self, env_key: str, secret_name: str | None = None) -> str:
        """Fetch a value from env or Secret Manager."""
        if self._use_secret_manager and secret_name:
            return self._fetch_secret(secret_name)
        value = os.getenv(env_key, "")
        if not value:
            raise ValueError(f"Missing required config: {env_key}")
        return value

    def _fetch_secret(self, secret_name: str) -> str:
        from google.cloud import secretmanager  # lazy import

        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{self._project_id}/secrets/{secret_name}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("utf-8")

    # --- WhatsApp ---
    @property
    def whatsapp_phone_number_id(self) -> str:
        return self._get("WHATSAPP_PHONE_NUMBER_ID", "photobridge-wa-phone-number-id")

    @property
    def whatsapp_access_token(self) -> str:
        return self._get("WHATSAPP_ACCESS_TOKEN", "photobridge-wa-access-token")

    @property
    def whatsapp_verify_token(self) -> str:
        return self._get("WHATSAPP_VERIFY_TOKEN", "photobridge-wa-verify-token")

    @property
    def whatsapp_app_secret(self) -> str:
        return self._get("WHATSAPP_APP_SECRET", "photobridge-wa-app-secret")

    # --- WordPress ---
    @property
    def wordpress_url(self) -> str:
        return self._get("WORDPRESS_URL", "photobridge-wp-url")

    @property
    def wordpress_username(self) -> str:
        return self._get("WORDPRESS_USERNAME", "photobridge-wp-username")

    @property
    def wordpress_app_password(self) -> str:
        return self._get("WORDPRESS_APP_PASSWORD", "photobridge-wp-app-password")

    # --- Google Drive ---
    @property
    def google_drive_folder_id(self) -> str:
        return self._get("GOOGLE_DRIVE_FOLDER_ID", "photobridge-drive-folder-id")

    @property
    def google_service_account_info(self) -> dict:
        """Returns parsed service account JSON."""
        if self._use_secret_manager:
            raw = self._fetch_secret("photobridge-service-account-json")
            return json.loads(raw)
        key_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_KEY_PATH", "")
        if key_path:
            with open(key_path) as f:
                return json.load(f)
        raise ValueError("No Google service account configured")


settings = Settings()
