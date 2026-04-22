"""
photobridge — Cloud Function entrypoint.

Receives WhatsApp webhook events from Meta, extracts photos, and fans
them out to all enabled destination plugins in priority order.

Adding a new destination
------------------------
1. Create photobridge/plugins/<name>.py subclassing BasePlugin
2. Import it here and add an instance to PLUGINS
3. Add its config vars to .env.example and deploy/deploy.sh
"""

import hashlib
import hmac
import logging
from collections import OrderedDict

import functions_framework
import requests
from flask import Request, jsonify

from photobridge.config import settings
from photobridge.handlers.whatsapp import WhatsAppHandler
from photobridge.plugins.ai_gate import AIGatePlugin
from photobridge.plugins.drive import DrivePlugin
from photobridge.plugins.facebook import FacebookPlugin
from photobridge.plugins.instagram import InstagramPlugin
from photobridge.plugins.wordpress import WordPressPlugin

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory dedup cache — prevents processing the same message twice when
# Meta retries a webhook after a slow response. Keyed by WhatsApp message ID.
# Works reliably for a single-instance bot; for multi-instance deployments
# use Firestore or Memorystore instead.
_seen_message_ids: OrderedDict = OrderedDict()
_DEDUP_CACHE_SIZE = 500


def _is_duplicate(message_id: str) -> bool:
    if message_id in _seen_message_ids:
        return True
    _seen_message_ids[message_id] = True
    if len(_seen_message_ids) > _DEDUP_CACHE_SIZE:
        _seen_message_ids.popitem(last=False)
    return False

# --- Plugin registry ---
# Plugins are sorted by priority at startup; lower number runs first.
# Add new destination plugins here.
PLUGINS = sorted(
    [
        WordPressPlugin(settings),
        DrivePlugin(settings),
        FacebookPlugin(settings),
        AIGatePlugin(settings),
        InstagramPlugin(settings),
    ],
    key=lambda p: p.priority,
)

_whatsapp = WhatsAppHandler(settings)


@functions_framework.http
def webhook(request: Request):
    """HTTP Cloud Function entrypoint."""

    # --- Instagram token auto-refresh (called by Cloud Scheduler) ---
    if request.method == "POST" and request.path == "/refresh-instagram-token":
        return _handle_token_refresh(request)

    # --- Webhook verification handshake (GET) ---
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        if mode == "subscribe" and token == settings.whatsapp_verify_token:
            logger.info("Webhook verified by Meta")
            return challenge, 200
        return "Forbidden", 403

    # --- Incoming event (POST) ---
    if request.method == "POST":
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not _verify_signature(request.get_data(), signature):
            logger.warning("Invalid webhook signature — ignoring")
            return "Unauthorized", 401

        payload = request.get_json(silent=True)
        if not payload:
            return "Bad Request", 400

        _process_payload(payload)
        # Always return 200 quickly; Meta will retry on non-200
        return jsonify({"status": "ok"}), 200

    return "Method Not Allowed", 405


def _verify_signature(body: bytes, signature_header: str) -> bool:
    """Verify the X-Hub-Signature-256 header from Meta."""
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        settings.whatsapp_app_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    provided = signature_header[len("sha256="):]
    return hmac.compare_digest(expected, provided)


def _process_payload(payload: dict) -> None:
    """Walk the webhook payload and process any image messages."""
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for message in value.get("messages", []):
                msg_id = message.get("id", "")
                if msg_id and _is_duplicate(msg_id):
                    logger.info("Skipping duplicate message %s", msg_id)
                    continue
                if not _is_relevant_message(message):
                    continue
                _handle_image_message(message)


def _is_relevant_message(message: dict) -> bool:
    """
    Accept the message if:
    - It is a direct message containing an image, OR
    - It is a group message containing an image where the bot is @mentioned
    """
    if message.get("type") != "image":
        return False

    context = message.get("context", {})
    mentioned_ids: list = message.get("mentions", [])
    is_group = "group_id" in message.get("conversation", {}) or bool(context.get("referred_product"))

    if is_group:
        return settings.whatsapp_phone_number_id in mentioned_ids
    return True  # DMs always accepted


def _handle_image_message(message: dict) -> None:
    """Download the image and fan it out through all triggered plugins."""
    image_id = message["image"]["id"]
    sender = message.get("from", "unknown")
    caption = message.get("image", {}).get("caption", "")

    logger.info("Processing image %s from %s", image_id, sender)

    try:
        image_bytes, mime_type = _whatsapp.download_media(image_id)
    except Exception:
        logger.exception("Failed to download media %s", image_id)
        _whatsapp.send_reply(sender, "Sorry, I couldn't download that image. Please try again.")
        return

    filename = f"{image_id}.jpg"
    errors = []
    # context accumulates URLs from each plugin so downstream plugins can use them
    # (e.g. Instagram reads context['wordpress'] for its public image URL)
    context: dict[str, str] = {}

    for plugin in PLUGINS:
        if not plugin.should_process(caption):
            logger.info("Plugin '%s' skipped (not triggered)", plugin.name)
            continue
        try:
            url = plugin.upload(image_bytes, filename, mime_type, caption, context)
            context[plugin.name] = url
            logger.info("Plugin '%s' succeeded: %s", plugin.name, url)
        except Exception:
            logger.exception("Plugin '%s' failed for image %s", plugin.name, image_id)
            errors.append(plugin.name)

    # Only count plugins that produced a URL (excludes gates like ai_gate)
    uploaded = [k for k, v in context.items() if v and not k.startswith("ai_gate")]

    if errors:
        _whatsapp.send_reply(sender, f"Photo received but upload failed for: {', '.join(errors)}.")
    elif uploaded:
        _whatsapp.send_reply(sender, f"Photo uploaded to: {', '.join(uploaded)}!")
    elif not context.get("ai_gate_rejected"):
        logger.info("No plugins triggered for image %s", image_id)

    if context.get("ai_gate_rejected"):
        reason = context.get("ai_gate_reason", "content policy")
        _whatsapp.send_reply(sender, f"Your photo was not posted to Instagram: {reason}.")


def _handle_token_refresh(request: Request):
    """Called by Cloud Scheduler monthly to rotate the Instagram access token."""
    secret = request.headers.get("X-Refresh-Secret", "")
    if not secret or not hmac.compare_digest(secret, settings.refresh_secret):
        logger.warning("Token refresh request with invalid secret")
        return "Unauthorized", 401

    try:
        _refresh_instagram_token()
        return jsonify({"status": "refreshed"}), 200
    except Exception:
        logger.exception("Failed to refresh Instagram token")
        return "Internal Server Error", 500


def _refresh_instagram_token() -> None:
    """Exchange the current Instagram token for a fresh 60-day token and update Secret Manager."""
    current_token = settings.instagram_access_token

    resp = requests.get(
        "https://graph.instagram.com/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": current_token},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    new_token = data.get("access_token")
    if not new_token:
        raise RuntimeError(f"Instagram token refresh returned no token: {resp.text}")

    from google.cloud import secretmanager
    client = secretmanager.SecretManagerServiceClient()
    secret_path = (
        f"projects/{settings.gcp_project_id}/secrets/photobridge-instagram-access-token"
    )
    client.add_secret_version(
        request={"parent": secret_path, "payload": {"data": new_token.encode()}}
    )
    logger.info(
        "Instagram access token refreshed; expires_in=%s seconds", data.get("expires_in")
    )
