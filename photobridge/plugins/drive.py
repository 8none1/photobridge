"""
Google Drive destination plugin.

Uploads images to a shared Drive folder using a service account.
Requires the Drive API to be enabled and the service account to have
Editor access on the target folder.
"""

import io
import logging

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from photobridge.plugins.base import BasePlugin

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


class DrivePlugin(BasePlugin):
    name = "drive"
    priority = 10

    def __init__(self, settings):
        super().__init__(settings)
        self._service = None

    def _get_service(self):
        if self._service is None:
            creds = service_account.Credentials.from_service_account_info(
                self._settings.google_service_account_info,
                scopes=SCOPES,
            )
            self._service = build("drive", "v3", credentials=creds, cache_discovery=False)
        return self._service

    def upload(
        self,
        image_bytes: bytes,
        filename: str,
        mime_type: str,
        caption: str,
        context: dict,
    ) -> str:
        service = self._get_service()

        file_metadata = {
            "name": filename,
            "parents": [self._settings.google_drive_folder_id],
        }
        if caption:
            file_metadata["description"] = caption

        media = MediaIoBaseUpload(
            io.BytesIO(image_bytes),
            mimetype=mime_type,
            resumable=False,
        )

        file = (
            service.files()
            .create(
                body=file_metadata,
                media_body=media,
                fields="id,webViewLink",
            )
            .execute()
        )

        url = file.get("webViewLink", "")
        logger.info("Drive upload complete: %s", file.get("id"))
        return url
