"""
Google Drive handler.

Uses a service account to upload photos to a shared Drive folder.
Requires the Drive API to be enabled in your GCP project and the
service account to have Editor access on the target folder.
"""

import io
import logging

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


class DriveHandler:
    def __init__(self, settings):
        self._settings = settings
        self._service = None

    def _get_service(self):
        if self._service is None:
            creds = service_account.Credentials.from_service_account_info(
                self._settings.google_service_account_info,
                scopes=SCOPES,
            )
            self._service = build("drive", "v3", credentials=creds, cache_discovery=False)
        return self._service

    def upload(self, image_bytes: bytes, filename: str, mime_type: str, description: str = "") -> str:
        """
        Upload image_bytes to the configured Drive folder.

        Returns the web view URL of the uploaded file.
        """
        service = self._get_service()

        file_metadata = {
            "name": filename,
            "parents": [self._settings.google_drive_folder_id],
        }
        if description:
            file_metadata["description"] = description

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

        logger.info("Drive upload complete: %s", file.get("id"))
        return file.get("webViewLink", "")
