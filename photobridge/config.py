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
    def google_drive_client_id(self) -> str:
        return self._get("GOOGLE_DRIVE_CLIENT_ID", "photobridge-drive-client-id")

    @property
    def google_drive_client_secret(self) -> str:
        return self._get("GOOGLE_DRIVE_CLIENT_SECRET", "photobridge-drive-client-secret")

    @property
    def google_drive_refresh_token(self) -> str:
        return self._get("GOOGLE_DRIVE_REFRESH_TOKEN", "photobridge-drive-refresh-token")

    # --- Facebook ---

    @property
    def facebook_page_id(self) -> str:
        return self._get("FACEBOOK_PAGE_ID", "photobridge-fb-page-id")

    @property
    def facebook_page_access_token(self) -> str:
        return self._get("FACEBOOK_PAGE_ACCESS_TOKEN", "photobridge-fb-page-access-token")

    # --- Instagram ---

    @property
    def instagram_user_id(self) -> str:
        return self._get("INSTAGRAM_USER_ID", "photobridge-instagram-user-id")

    @property
    def instagram_access_token(self) -> str:
        return self._get("INSTAGRAM_ACCESS_TOKEN", "photobridge-instagram-access-token")


settings = Settings()
