"""
WhatsApp Cloud API handler.

Responsibilities:
- Download media (images) using the media ID from a webhook payload
- Send text reply messages back to a sender
"""

import logging

import requests

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com/v19.0"


class WhatsAppHandler:
    def __init__(self, settings):
        self._settings = settings

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._settings.whatsapp_access_token}"}

    def download_media(self, media_id: str) -> tuple[bytes, str]:
        """
        Fetch media bytes from WhatsApp.

        Returns (image_bytes, mime_type).
        """
        # Step 1: resolve the media URL
        meta_url = f"{GRAPH_API_BASE}/{media_id}"
        resp = requests.get(meta_url, headers=self._auth_headers(), timeout=15)
        resp.raise_for_status()
        media_info = resp.json()
        download_url = media_info["url"]
        mime_type = media_info.get("mime_type", "image/jpeg")

        # Step 2: download the actual bytes
        download_resp = requests.get(download_url, headers=self._auth_headers(), timeout=30)
        download_resp.raise_for_status()

        return download_resp.content, mime_type

    def send_reply(self, recipient_phone: str, text: str) -> None:
        """Send a plain-text reply to a WhatsApp number."""
        url = f"{GRAPH_API_BASE}/{self._settings.whatsapp_phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient_phone,
            "type": "text",
            "text": {"body": text},
        }
        try:
            resp = requests.post(url, json=payload, headers=self._auth_headers(), timeout=10)
            resp.raise_for_status()
        except requests.RequestException:
            # Reply failures are non-fatal — the upload may have succeeded
            logger.warning("Failed to send reply to %s", recipient_phone)
