"""
Facebook destination plugin.

Posts images directly to a Facebook Page using the Graph API.
Requires a long-lived Page access token with pages_manage_posts permission.
"""

import logging

import requests

from photobridge.plugins.base import BasePlugin

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com/v19.0"


class FacebookPlugin(BasePlugin):
    name = "facebook"
    priority = 10

    def upload(
        self,
        image_bytes: bytes,
        filename: str,
        mime_type: str,
        caption: str,
        context: dict,
    ) -> str:
        page_id = self._settings.facebook_page_id
        token = self._settings.facebook_page_access_token

        resp = requests.post(
            f"{GRAPH_API_BASE}/{page_id}/photos",
            data={"caption": caption, "access_token": token},
            files={"source": (filename, image_bytes, mime_type)},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        post_id = data.get("post_id") or data.get("id", "")
        url = f"https://www.facebook.com/permalink.php?story_fbid={post_id}&id={page_id}" if post_id else ""
        logger.info("Facebook post published: %s", post_id)
        return url
