"""Pytest configuration and shared fixtures."""

import pytest
import functions_framework


@pytest.fixture
def client():
    """Return a test client for the Cloud Function."""
    from main import webhook

    app = functions_framework.create_app(target="webhook", source="main.py")
    app.testing = True
    with app.test_client() as c:
        yield c
