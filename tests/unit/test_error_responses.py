"""Tests for check_api_response() and command exit codes on API errors."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from scrapingbee_cli.cli import cli
from scrapingbee_cli.cli_utils import check_api_response


class TestCheckApiResponse:
    """check_api_response() exits 1 on 4xx/5xx, passes on 2xx/3xx."""

    def test_200_does_not_exit(self):
        check_api_response(b'{"ok": true}', 200)

    def test_399_does_not_exit(self):
        check_api_response(b"redirect", 399)

    def test_400_exits_with_1(self):
        with pytest.raises(SystemExit) as exc_info:
            check_api_response(b'{"error": "bad request"}', 400)
        assert exc_info.value.code == 1

    def test_401_exits_with_1(self):
        with pytest.raises(SystemExit) as exc_info:
            check_api_response(b'{"error": "unauthorized"}', 401)
        assert exc_info.value.code == 1

    def test_500_exits_with_1(self):
        with pytest.raises(SystemExit) as exc_info:
            check_api_response(b"server error", 500)
        assert exc_info.value.code == 1

    def test_error_status_printed_to_stderr(self, capsys):
        with pytest.raises(SystemExit):
            check_api_response(b'{"error": "forbidden"}', 403)
        assert "403" in capsys.readouterr().err


def _mock_client_cls(method_name: str, status_code: int, body: bytes = b'{"error": "test"}'):
    """Return a mock Client class whose context manager yields a client with the given response."""
    mock_client = AsyncMock()
    getattr(mock_client, method_name).return_value = (body, {}, status_code)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return MagicMock(return_value=mock_client)


@pytest.mark.parametrize(
    "cmd_args,client_module,method_name",
    [
        (["google", "python"], "scrapingbee_cli.commands.google.Client", "google_search"),
        (
            ["fast-search", "python"],
            "scrapingbee_cli.commands.fast_search.Client",
            "fast_search",
        ),
        (
            ["amazon-product", "B001234"],
            "scrapingbee_cli.commands.amazon.Client",
            "amazon_product",
        ),
        (
            ["amazon-search", "laptop"],
            "scrapingbee_cli.commands.amazon.Client",
            "amazon_search",
        ),
        (
            ["walmart-search", "laptop"],
            "scrapingbee_cli.commands.walmart.Client",
            "walmart_search",
        ),
        (
            ["walmart-product", "12345"],
            "scrapingbee_cli.commands.walmart.Client",
            "walmart_product",
        ),
        (
            ["youtube-search", "python"],
            "scrapingbee_cli.commands.youtube.Client",
            "youtube_search",
        ),
        (
            ["youtube-metadata", "dQw4w9WgXcQ"],
            "scrapingbee_cli.commands.youtube.Client",
            "youtube_metadata",
        ),
        (
            ["chatgpt", "hello"],
            "scrapingbee_cli.commands.chatgpt.Client",
            "chatgpt",
        ),
        (
            ["scrape", "https://example.com"],
            "scrapingbee_cli.commands.scrape.Client",
            "scrape",
        ),
    ],
)
def test_command_exits_1_on_4xx(cmd_args, client_module, method_name, monkeypatch):
    """Single-call mode exits with code 1 when the API returns a 4xx response."""
    monkeypatch.setenv("SCRAPINGBEE_API_KEY", "test-key")
    mock_cls = _mock_client_cls(method_name, 401)

    with patch(client_module, mock_cls):
        result = CliRunner().invoke(cli, cmd_args)

    assert result.exit_code == 1, (
        f"`{cmd_args[0]}` should exit 1 on HTTP 401, got {result.exit_code}. "
        f"Output: {result.output}"
    )


def test_command_succeeds_on_200(monkeypatch):
    """Single-call mode exits 0 on a successful 200 response."""
    monkeypatch.setenv("SCRAPINGBEE_API_KEY", "test-key")
    mock_cls = _mock_client_cls("google_search", 200, b'{"results": []}')

    with patch("scrapingbee_cli.commands.google.Client", mock_cls):
        result = CliRunner().invoke(cli, ["google", "python"])

    assert result.exit_code == 0, (
        f"Expected exit 0 on 200, got {result.exit_code}. Output: {result.output}"
    )
