"""Unit tests for config module."""

from __future__ import annotations

import os

import pytest

from scrapingbee_cli.config import (
    BASE_URL,
    ENV_API_KEY,
    get_api_key,
    get_api_key_if_set,
    load_dotenv,
    remove_api_key_from_dotenv,
    save_api_key_to_dotenv,
)


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
    with pytest.raises(ValueError, match="API key not set"):
        get_api_key(None)
    with pytest.raises(ValueError, match="API key not set"):
        get_api_key("")  # empty string → fallback to env → not set → raise


def test_get_api_key_flag_overrides_env(monkeypatch):
    monkeypatch.setenv(ENV_API_KEY, "env-key")
    assert get_api_key("flag-key") == "flag-key"


def test_get_api_key_if_set_returns_none_when_missing(monkeypatch):
    monkeypatch.delenv(ENV_API_KEY, raising=False)
    assert get_api_key_if_set(None) is None
    assert get_api_key_if_set("") is None


def test_get_api_key_if_set_returns_flag(monkeypatch):
    monkeypatch.delenv(ENV_API_KEY, raising=False)
    assert get_api_key_if_set("flag-key") == "flag-key"


def test_get_api_key_if_set_returns_env(monkeypatch):
    monkeypatch.setenv(ENV_API_KEY, "env-key")
    assert get_api_key_if_set(None) == "env-key"


def test_load_dotenv_sets_from_file(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("SCRAPINGBEE_API_KEY=from-dotenv\n")
    monkeypatch.delenv(ENV_API_KEY, raising=False)
    monkeypatch.chdir(tmp_path)  # load_dotenv evaluates Path.cwd() at call time
    from scrapingbee_cli import config

    monkeypatch.setattr(config, "DOTENV_HOME", tmp_path / "nonexistent.env")
    load_dotenv()
    assert os.environ.get(ENV_API_KEY) == "from-dotenv"


def test_load_dotenv_does_not_override_existing_env(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("SCRAPINGBEE_API_KEY=from-dotenv\n")
    monkeypatch.setenv(ENV_API_KEY, "already-set")
    monkeypatch.chdir(tmp_path)  # load_dotenv evaluates Path.cwd() at call time
    from scrapingbee_cli import config

    monkeypatch.setattr(config, "DOTENV_HOME", tmp_path / "nonexistent.env")
    load_dotenv()
    assert os.environ.get(ENV_API_KEY) == "already-set"


def test_save_and_remove_api_key_dotenv(monkeypatch, tmp_path):
    from scrapingbee_cli import config

    auth_file = tmp_path / ".env"
    monkeypatch.setattr(config, "DOTENV_HOME", auth_file)
    monkeypatch.setattr(config, "auth_config_path", lambda: auth_file)

    assert remove_api_key_from_dotenv() is False
    path = save_api_key_to_dotenv("test-key-123")
    assert path == auth_file
    assert auth_file.read_text() == 'SCRAPINGBEE_API_KEY="test-key-123"\n'

    assert remove_api_key_from_dotenv() is True
    assert not auth_file.exists()

    # Remove again is no-op
    assert remove_api_key_from_dotenv() is False


def test_save_api_key_preserves_other_vars(monkeypatch, tmp_path):
    from scrapingbee_cli import config

    auth_file = tmp_path / ".env"
    auth_file.parent.mkdir(parents=True, exist_ok=True)
    auth_file.write_text('OTHER_VAR="other"\n')
    monkeypatch.setattr(config, "DOTENV_HOME", auth_file)
    monkeypatch.setattr(config, "auth_config_path", lambda: auth_file)

    save_api_key_to_dotenv("bee-key")
    content = auth_file.read_text()
    assert "SCRAPINGBEE_API_KEY" in content
    assert "OTHER_VAR" in content
    assert "bee-key" in content
    assert "other" in content


def test_remove_api_key_keeps_other_vars(monkeypatch, tmp_path):
    from scrapingbee_cli import config

    auth_file = tmp_path / ".env"
    auth_file.parent.mkdir(parents=True, exist_ok=True)
    auth_file.write_text('SCRAPINGBEE_API_KEY="old"\nOTHER_VAR="other"\n')
    monkeypatch.setattr(config, "DOTENV_HOME", auth_file)
    monkeypatch.setattr(config, "auth_config_path", lambda: auth_file)

    remove_api_key_from_dotenv()
    assert auth_file.read_text().strip() == 'OTHER_VAR="other"'
