"""Unit tests for config module."""

from __future__ import annotations

import pytest

from scrapingbee_cli.config import BASE_URL, ENV_API_KEY, get_api_key


def test_base_url():
    assert BASE_URL == "https://app.scrapingbee.com/api/v1"


def test_get_api_key_from_flag():
    assert get_api_key("my-key-123") == "my-key-123"


def test_get_api_key_empty_string_uses_env(monkeypatch):
    """Empty string is falsy, so get_api_key('') falls back to env."""
    monkeypatch.setenv(ENV_API_KEY, "env-key")
    assert get_api_key("") == "env-key"


def test_get_api_key_from_env(monkeypatch):
    monkeypatch.delenv(ENV_API_KEY, raising=False)
    monkeypatch.setenv(ENV_API_KEY, "env-key-456")
    assert get_api_key(None) == "env-key-456"


def test_get_api_key_missing_raises(monkeypatch):
    monkeypatch.delenv(ENV_API_KEY, raising=False)
    with pytest.raises(ValueError, match="API key not provided"):
        get_api_key(None)
    with pytest.raises(ValueError, match="API key not provided"):
        get_api_key("")  # empty string → fallback to env → not set → raise


def test_get_api_key_flag_overrides_env(monkeypatch):
    monkeypatch.setenv(ENV_API_KEY, "env-key")
    assert get_api_key("flag-key") == "flag-key"
