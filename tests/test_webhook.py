"""
Tests for the webhook entrypoint.

Uses functions-framework test client and mocks external calls.
"""

import hashlib
import hmac
import json
from unittest.mock import patch

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
    monkeypatch.setenv("INSTAGRAM_USER_ID", "ig_user_123")
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "ig_token")


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
    """All enabled plugins should be called for a standard DM image."""
    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "type": "image",
                        "from": "447700900000",
                        "image": {"id": "media-abc", "caption": "Test photo"},
                    }]
                }
            }]
        }]
    }
    body = json.dumps(payload).encode()
    sig = _make_signature(body, APP_SECRET)

    with patch("main._whatsapp.download_media", return_value=(b"imgdata", "image/jpeg")), \
         patch("photobridge.plugins.wordpress.WordPressPlugin.upload", return_value="https://wp.example.com/img.jpg") as wp_mock, \
         patch("photobridge.plugins.drive.DrivePlugin.upload", return_value="https://drive.link/file") as drive_mock, \
         patch("photobridge.plugins.instagram.InstagramPlugin.upload", return_value="https://instagram.com/p/abc") as ig_mock, \
         patch("main._whatsapp.send_reply"):
        resp = client.post(
            "/",
            data=body,
            content_type="application/json",
            headers={"X-Hub-Signature-256": sig},
        )

    assert resp.status_code == 200
    wp_mock.assert_called_once()
    drive_mock.assert_called_once()
    ig_mock.assert_called_once()


def test_plugin_require_tag_skips_untagged(client, monkeypatch):
    """When REQUIRE_TAG is true, photos without the tag should not trigger the plugin."""
    monkeypatch.setenv("PLUGIN_INSTAGRAM_REQUIRE_TAG", "true")
    monkeypatch.setenv("PLUGIN_INSTAGRAM_TAG", "#instagram")

    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "type": "image",
                        "from": "447700900000",
                        "image": {"id": "media-xyz", "caption": "No tag here"},
                    }]
                }
            }]
        }]
    }
    body = json.dumps(payload).encode()
    sig = _make_signature(body, APP_SECRET)

    with patch("main._whatsapp.download_media", return_value=(b"imgdata", "image/jpeg")), \
         patch("photobridge.plugins.wordpress.WordPressPlugin.upload", return_value="https://wp.example.com/img.jpg"), \
         patch("photobridge.plugins.drive.DrivePlugin.upload", return_value="https://drive.link/file"), \
         patch("photobridge.plugins.instagram.InstagramPlugin.upload") as ig_mock, \
         patch("main._whatsapp.send_reply"):
        resp = client.post(
            "/",
            data=body,
            content_type="application/json",
            headers={"X-Hub-Signature-256": sig},
        )

    assert resp.status_code == 200
    ig_mock.assert_not_called()


def test_plugin_require_tag_fires_when_tagged(client, monkeypatch):
    """When REQUIRE_TAG is true and the tag is present, the plugin should fire."""
    monkeypatch.setenv("PLUGIN_INSTAGRAM_REQUIRE_TAG", "true")
    monkeypatch.setenv("PLUGIN_INSTAGRAM_TAG", "#instagram")

    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "type": "image",
                        "from": "447700900000",
                        "image": {"id": "media-xyz", "caption": "Great shot! #instagram"},
                    }]
                }
            }]
        }]
    }
    body = json.dumps(payload).encode()
    sig = _make_signature(body, APP_SECRET)

    with patch("main._whatsapp.download_media", return_value=(b"imgdata", "image/jpeg")), \
         patch("photobridge.plugins.wordpress.WordPressPlugin.upload", return_value="https://wp.example.com/img.jpg"), \
         patch("photobridge.plugins.drive.DrivePlugin.upload", return_value="https://drive.link/file"), \
         patch("photobridge.plugins.instagram.InstagramPlugin.upload", return_value="https://instagram.com/p/abc") as ig_mock, \
         patch("main._whatsapp.send_reply"):
        resp = client.post(
            "/",
            data=body,
            content_type="application/json",
            headers={"X-Hub-Signature-256": sig},
        )

    assert resp.status_code == 200
    ig_mock.assert_called_once()


def test_plugin_disabled_is_skipped(client, monkeypatch):
    """A disabled plugin should never be called."""
    monkeypatch.setenv("PLUGIN_INSTAGRAM_ENABLED", "false")

    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "type": "image",
                        "from": "447700900000",
                        "image": {"id": "media-xyz", "caption": "#instagram"},
                    }]
                }
            }]
        }]
    }
    body = json.dumps(payload).encode()
    sig = _make_signature(body, APP_SECRET)

    with patch("main._whatsapp.download_media", return_value=(b"imgdata", "image/jpeg")), \
         patch("photobridge.plugins.wordpress.WordPressPlugin.upload", return_value="https://wp.example.com/img.jpg"), \
         patch("photobridge.plugins.drive.DrivePlugin.upload", return_value="https://drive.link/file"), \
         patch("photobridge.plugins.instagram.InstagramPlugin.upload") as ig_mock, \
         patch("main._whatsapp.send_reply"):
        resp = client.post(
            "/",
            data=body,
            content_type="application/json",
            headers={"X-Hub-Signature-256": sig},
        )

    assert resp.status_code == 200
    ig_mock.assert_not_called()
