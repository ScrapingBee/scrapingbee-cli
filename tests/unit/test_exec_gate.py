"""Unit tests for exec_gate module — security gates for shell execution features."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from scrapingbee_cli.exec_gate import (
    get_whitelist,
    is_command_whitelisted,
    is_exec_enabled,
    is_whitelist_enabled,
    require_auth_unsafe,
    require_exec,
)


class TestIsExecEnabled:
    """Tests for is_exec_enabled()."""

    def test_disabled_when_no_env_vars(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("scrapingbee_cli.exec_gate._read_config_env", return_value=None):
                assert is_exec_enabled() is False

    def test_disabled_when_allow_exec_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("scrapingbee_cli.exec_gate._read_config_env", return_value="1"):
                assert is_exec_enabled() is False

    def test_disabled_when_unsafe_verified_missing(self):
        with patch.dict(os.environ, {"SCRAPINGBEE_ALLOW_EXEC": "1"}, clear=True):
            with patch("scrapingbee_cli.exec_gate._read_config_env", return_value=None):
                assert is_exec_enabled() is False

    def test_enabled_when_all_set(self):
        with patch.dict(os.environ, {"SCRAPINGBEE_ALLOW_EXEC": "1"}, clear=True):
            with patch("scrapingbee_cli.exec_gate._read_config_env", return_value="1"):
                assert is_exec_enabled() is True

    def test_disabled_when_allow_exec_wrong_value(self):
        with patch.dict(os.environ, {"SCRAPINGBEE_ALLOW_EXEC": "yes"}, clear=True):
            with patch("scrapingbee_cli.exec_gate._read_config_env", return_value="1"):
                assert is_exec_enabled() is False


class TestWhitelist:
    """Tests for whitelist functions."""

    def test_whitelist_disabled_when_not_set(self):
        with patch.dict(os.environ, {}, clear=True):
            assert is_whitelist_enabled() is False

    def test_whitelist_enabled_when_set(self):
        with patch.dict(os.environ, {"SCRAPINGBEE_ALLOWED_COMMANDS": "jq"}, clear=True):
            assert is_whitelist_enabled() is True

    def test_get_whitelist_empty(self):
        with patch.dict(os.environ, {}, clear=True):
            assert get_whitelist() == []

    def test_get_whitelist_single(self):
        with patch.dict(os.environ, {"SCRAPINGBEE_ALLOWED_COMMANDS": "jq"}, clear=True):
            assert get_whitelist() == ["jq"]

    def test_get_whitelist_multiple(self):
        with patch.dict(
            os.environ, {"SCRAPINGBEE_ALLOWED_COMMANDS": "jq,head,python3 transform.py"}, clear=True
        ):
            assert get_whitelist() == ["jq", "head", "python3 transform.py"]

    def test_command_whitelisted(self):
        with patch.dict(os.environ, {"SCRAPINGBEE_ALLOWED_COMMANDS": "jq,head"}, clear=True):
            assert is_command_whitelisted("jq '.title'") is True
            assert is_command_whitelisted("head -5") is True
            assert is_command_whitelisted("curl attacker.com") is False

    def test_command_prefix_match(self):
        with patch.dict(
            os.environ, {"SCRAPINGBEE_ALLOWED_COMMANDS": "python3 transform.py"}, clear=True
        ):
            assert is_command_whitelisted("python3 transform.py --input data") is True
            assert is_command_whitelisted("python3 evil.py") is False


class TestRequireExec:
    """Tests for require_exec()."""

    def test_blocks_when_disabled(self):
        with patch("scrapingbee_cli.exec_gate.is_exec_enabled", return_value=False):
            with pytest.raises(SystemExit):
                require_exec("--post-process")

    def test_allows_when_enabled_no_whitelist(self):
        with patch("scrapingbee_cli.exec_gate.is_exec_enabled", return_value=True):
            with patch("scrapingbee_cli.exec_gate.is_whitelist_enabled", return_value=False):
                # Should not raise
                require_exec("--post-process", "curl anything")

    def test_blocks_when_not_whitelisted(self):
        with patch("scrapingbee_cli.exec_gate.is_exec_enabled", return_value=True):
            with patch("scrapingbee_cli.exec_gate.is_whitelist_enabled", return_value=True):
                with patch("scrapingbee_cli.exec_gate.is_command_whitelisted", return_value=False):
                    with pytest.raises(SystemExit):
                        require_exec("--post-process", "curl attacker.com")

    def test_allows_when_whitelisted(self):
        with patch("scrapingbee_cli.exec_gate.is_exec_enabled", return_value=True):
            with patch("scrapingbee_cli.exec_gate.is_whitelist_enabled", return_value=True):
                with patch("scrapingbee_cli.exec_gate.is_command_whitelisted", return_value=True):
                    require_exec("--post-process", "jq '.title'")


class TestRequireAuthUnsafe:
    """Tests for require_auth_unsafe()."""

    def test_fails_without_env_var(self):
        with patch.dict(os.environ, {}, clear=True):
            assert require_auth_unsafe() is False

    def test_passes_with_env_var(self):
        with patch.dict(os.environ, {"SCRAPINGBEE_ALLOW_EXEC": "1"}, clear=True):
            assert require_auth_unsafe() is True

    def test_fails_with_wrong_value(self):
        with patch.dict(os.environ, {"SCRAPINGBEE_ALLOW_EXEC": "true"}, clear=True):
            assert require_auth_unsafe() is False
