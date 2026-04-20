"""
photobridge — Cloud Function entrypoint.

Receives WhatsApp webhook events from Meta, extracts photos, and fans
them out to Google Drive and WordPress.
"""

import hashlib
import hmac
import json
import logging
import os

import functions_framework
from flask import Request, jsonify

from photobridge.config import settings
from photobridge.handlers.whatsapp import WhatsAppHandler
from photobridge.handlers.drive import DriveHandler
from photobridge.handlers.wordpress import WordPressHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_whatsapp = WhatsAppHandler(settings)
_drive = DriveHandler(settings)
_wordpress = WordPressHandler(settings)


@functions_framework.http
def webhook(request: Request):
    """HTTP Cloud Function entrypoint."""

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
        # Validate payload signature
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
            messages = value.get("messages", [])
            for message in messages:
                if not _is_relevant_message(message):
                    continue
                _handle_image_message(message, value)


def _is_relevant_message(message: dict) -> bool:
    """
    Accept the message if:
    - It is a direct message containing an image, OR
    - It is a group message containing an image where the bot is mentioned
    """
    if message.get("type") != "image":
        return False

    context = message.get("context", {})
    mentioned_ids: list = message.get("mentions", [])
    is_group = "group_id" in message.get("conversation", {}) or bool(context.get("referred_product"))

    if is_group:
        return settings.whatsapp_phone_number_id in mentioned_ids
    return True  # DMs always accepted


def _handle_image_message(message: dict, value: dict) -> None:
    """Download the image and fan out to Drive and WordPress."""
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

    # Upload to Google Drive
    try:
        drive_url = _drive.upload(image_bytes, filename, mime_type, caption)
        logger.info("Uploaded to Drive: %s", drive_url)
    except Exception:
        logger.exception("Drive upload failed for %s", image_id)
        errors.append("Google Drive")

    # Upload to WordPress
    try:
        wp_url = _wordpress.upload(image_bytes, filename, mime_type, caption)
        logger.info("Uploaded to WordPress: %s", wp_url)
    except Exception:
        logger.exception("WordPress upload failed for %s", image_id)
        errors.append("WordPress")

    # Confirm back to the sender
    if errors:
        _whatsapp.send_reply(sender, f"Photo received but upload failed for: {', '.join(errors)}.")
    else:
        _whatsapp.send_reply(sender, "Photo uploaded to the gallery and Drive!")
