"""
WordPress destination plugin.

Uploads images to the WordPress Media Library using Application Passwords
(WP 5.6+). Runs at priority 10 so its public URL is available to
downstream plugins (e.g. Instagram) via context['wordpress'].
"""

import logging

import requests
from requests.auth import HTTPBasicAuth

from photobridge.plugins.base import BasePlugin

logger = logging.getLogger(__name__)


class WordPressPlugin(BasePlugin):
    name = "wordpress"
    priority = 10

    def _auth(self):
        return HTTPBasicAuth(
            self._settings.wordpress_username,
            self._settings.wordpress_app_password,
        )

    def upload(
        self,
        image_bytes: bytes,
        filename: str,
        mime_type: str,
        caption: str,
        context: dict,
    ) -> str:
        url = f"{self._settings.wordpress_url.rstrip('/')}/wp-json/wp/v2/media"

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": mime_type,
        }

        resp = requests.post(
            url,
            data=image_bytes,
            headers=headers,
            auth=self._auth(),
            timeout=30,
        )
        resp.raise_for_status()

        media = resp.json()
        media_id = media.get("id")
        media_url = media.get("source_url", "")

        if caption and media_id:
            self._update_caption(media_id, caption)

        logger.info("WordPress upload complete: %s", media_url)
        return media_url

    def _update_caption(self, media_id: int, caption: str) -> None:
        url = f"{self._settings.wordpress_url.rstrip('/')}/wp-json/wp/v2/media/{media_id}"
        try:
            resp = requests.post(
                url,
                json={"caption": caption},
                auth=self._auth(),
                timeout=10,
            )
            resp.raise_for_status()
        except requests.RequestException:
            logger.warning("Failed to set caption on media %s", media_id)
