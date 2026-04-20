"""
Tests for the webhook entrypoint.

Uses functions-framework test client and mocks external calls.
"""

import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import pytest


VERIFY_TOKEN = "test-verify-token"
APP_SECRET = "test-app-secret"


def _make_signature(body: bytes, secret: str) -> str:
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


@pytest.fixture(autouse=True)
def mock_settings(monkeypatch):
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "12345")
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "token")
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", VERIFY_TOKEN)
    monkeypatch.setenv("WHATSAPP_APP_SECRET", APP_SECRET)
    monkeypatch.setenv("WORDPRESS_URL", "https://example.com")
    monkeypatch.setenv("WORDPRESS_USERNAME", "admin")
    monkeypatch.setenv("WORDPRESS_APP_PASSWORD", "pass")
    monkeypatch.setenv("GOOGLE_DRIVE_FOLDER_ID", "folder123")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_KEY_PATH", "/dev/null")


def test_webhook_verification_success(client):
    resp = client.get(
        "/?hub.mode=subscribe"
        f"&hub.verify_token={VERIFY_TOKEN}"
        "&hub.challenge=abc123"
    )
    assert resp.status_code == 200
    assert resp.data == b"abc123"


def test_webhook_verification_wrong_token(client):
    resp = client.get(
        "/?hub.mode=subscribe"
        "&hub.verify_token=wrong"
        "&hub.challenge=abc123"
    )
    assert resp.status_code == 403


def test_webhook_rejects_bad_signature(client):
    body = b'{"entry": []}'
    resp = client.post(
        "/",
        data=body,
        content_type="application/json",
        headers={"X-Hub-Signature-256": "sha256=badsig"},
    )
    assert resp.status_code == 401


def test_webhook_processes_image_message(client):
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "type": "image",
                                    "from": "447700900000",
                                    "image": {"id": "media-abc", "caption": "Test photo"},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    body = json.dumps(payload).encode()
    sig = _make_signature(body, APP_SECRET)

    with patch("main._whatsapp.download_media", return_value=(b"imgdata", "image/jpeg")), \
         patch("main._drive.upload", return_value="https://drive.link"), \
         patch("main._wordpress.upload", return_value="https://wp.link/img.jpg"), \
         patch("main._whatsapp.send_reply"):
        resp = client.post(
            "/",
            data=body,
            content_type="application/json",
            headers={"X-Hub-Signature-256": sig},
        )

    assert resp.status_code == 200
