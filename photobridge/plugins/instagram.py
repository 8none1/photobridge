"""
Instagram destination plugin.

Publishes images to an Instagram Business or Creator account using the
Instagram Graph API (Meta).

Requirements:
- Instagram Business or Creator account linked to a Facebook Page
- A Meta App with instagram_content_publish and instagram_basic permissions
- A long-lived User Access Token with those permissions

Image URL dependency:
  Instagram's API requires a publicly accessible image URL — it cannot
  receive raw bytes. This plugin reads context['wordpress'] for the URL
  produced by the WordPress plugin (which must run first, priority < 20).

  If WordPress is disabled, set PLUGIN_INSTAGRAM_IMAGE_SOURCE to the name
  of another plugin whose URL should be used, or raise the issue as a
  future GCS fallback.

Configuration:
  INSTAGRAM_USER_ID          Your Instagram Business account user ID
  INSTAGRAM_ACCESS_TOKEN     Long-lived User Access Token

  PLUGIN_INSTAGRAM_ENABLED       true/false (default: true)
  PLUGIN_INSTAGRAM_REQUIRE_TAG   true/false (default: false)
  PLUGIN_INSTAGRAM_TAG           hashtag to require (default: #instagram)
  PLUGIN_INSTAGRAM_IMAGE_SOURCE  plugin name to read URL from (default: wordpress)
"""

import logging
import time

import requests

from photobridge.plugins.base import BasePlugin

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com/v19.0"

# How long to wait (seconds) between creating a container and publishing it.
# Instagram needs a moment to fetch and process the image.
_PUBLISH_DELAY = 2


class InstagramPlugin(BasePlugin):
    name = "instagram"
    priority = 20  # Runs after WordPress (priority 10) so its URL is available

    @property
    def _image_source(self) -> str:
        """Which plugin's URL to use as the image source."""
        return self._env("IMAGE_SOURCE", "wordpress")

    def _auth_params(self) -> dict:
        return {"access_token": self._settings.instagram_access_token}

    def upload(
        self,
        image_bytes: bytes,
        filename: str,
        mime_type: str,
        caption: str,
        context: dict,
    ) -> str:
        if context.get("ai_gate_rejected"):
            logger.info("Instagram skipped — blocked by AI gate")
            return ""

        image_url = context.get(self._image_source, "")
        if not image_url:
            raise RuntimeError(
                f"Instagram plugin requires a public image URL from the "
                f"'{self._image_source}' plugin, but it produced no URL. "
                f"Ensure PLUGIN_{self._image_source.upper()}_ENABLED=true "
                f"and that it runs before Instagram (lower priority number)."
            )

        user_id = self._settings.instagram_user_id

        # Step 1: Create a media container
        container_id = self._create_container(user_id, image_url, caption)

        # Step 2: Wait briefly for Instagram to fetch the image
        time.sleep(_PUBLISH_DELAY)

        # Step 3: Publish
        post_id = self._publish_container(user_id, container_id)

        post_url = f"https://www.instagram.com/p/{post_id}/"
        logger.info("Instagram post published: %s", post_url)
        return post_url

    def _create_container(self, user_id: str, image_url: str, caption: str) -> str:
        url = f"{GRAPH_API_BASE}/{user_id}/media"
        params = {
            **self._auth_params(),
            "image_url": image_url,
            "caption": caption,
        }
        resp = requests.post(url, params=params, timeout=30)
        resp.raise_for_status()
        container_id = resp.json().get("id")
        if not container_id:
            raise RuntimeError(f"Instagram container creation returned no ID: {resp.text}")
        logger.info("Instagram container created: %s", container_id)
        return container_id

    def _publish_container(self, user_id: str, container_id: str) -> str:
        url = f"{GRAPH_API_BASE}/{user_id}/media_publish"
        params = {
            **self._auth_params(),
            "creation_id": container_id,
        }
        resp = requests.post(url, params=params, timeout=30)
        resp.raise_for_status()
        post_id = resp.json().get("id")
        if not post_id:
            raise RuntimeError(f"Instagram publish returned no post ID: {resp.text}")
        return post_id
