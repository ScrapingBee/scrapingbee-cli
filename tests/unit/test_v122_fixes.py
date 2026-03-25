"""Unit tests for post-v1.2.2 changes.

Covers:
1. ChatGPT --search, --add-html, --country-code flags
2. --search false silently ignored (param not sent)
3. ensure_url_scheme() auto-prepend https://
4. _cli_allowed_domains rename (Scrapy attribute conflict fix)
5. Screenshot warning removed
6. Exact credit costs (credits.py + write_output credit_cost param)
7. DepthMiddleware disabled in crawl settings
"""

from __future__ import annotations

import asyncio
import json
from io import StringIO
from unittest.mock import AsyncMock, patch

import click
import pytest
from click.testing import CliRunner

from scrapingbee_cli.cli_utils import ensure_url_scheme
from scrapingbee_cli.credits import (
    ESTIMATED_CREDITS,
    amazon_credits,
    chatgpt_credits,
    fast_search_credits,
    google_credits,
    walmart_credits,
    youtube_credits,
)


# =============================================================================
# 1-2. ChatGPT client params
# =============================================================================


class TestChatGPTClientParams:
    """Tests for Client.chatgpt() param handling."""

    def test_chatgpt_search_true_sends_param(self):
        async def run():
            from scrapingbee_cli.client import Client

            client = Client("fake-key")
            with patch.object(client, "_get_with_retry", new_callable=AsyncMock) as m:
                m.return_value = (b'{"result": "ok"}', {}, 200)
                await client.chatgpt("hello", search=True)
            args, kwargs = m.call_args
            params = args[1]
            assert params["search"] == "true"
            assert params["prompt"] == "hello"

        asyncio.run(run())

    def test_chatgpt_search_false_not_sent(self):
        """--search false should NOT send the search param at all."""

        async def run():
            from scrapingbee_cli.client import Client

            client = Client("fake-key")
            with patch.object(client, "_get_with_retry", new_callable=AsyncMock) as m:
                m.return_value = (b'{"result": "ok"}', {}, 200)
                await client.chatgpt("hello", search=False)
            args, kwargs = m.call_args
            params = args[1]
            assert "search" not in params

        asyncio.run(run())

    def test_chatgpt_search_none_not_sent(self):
        """When search is not specified, param should not be sent."""

        async def run():
            from scrapingbee_cli.client import Client

            client = Client("fake-key")
            with patch.object(client, "_get_with_retry", new_callable=AsyncMock) as m:
                m.return_value = (b'{"result": "ok"}', {}, 200)
                await client.chatgpt("hello")
            args, kwargs = m.call_args
            params = args[1]
            assert "search" not in params

        asyncio.run(run())

    def test_chatgpt_add_html_true(self):
        async def run():
            from scrapingbee_cli.client import Client

            client = Client("fake-key")
            with patch.object(client, "_get_with_retry", new_callable=AsyncMock) as m:
                m.return_value = (b'{"result": "ok"}', {}, 200)
                await client.chatgpt("hello", add_html=True)
            params = m.call_args[0][1]
            assert params["add_html"] == "true"

        asyncio.run(run())

    def test_chatgpt_add_html_false(self):
        async def run():
            from scrapingbee_cli.client import Client

            client = Client("fake-key")
            with patch.object(client, "_get_with_retry", new_callable=AsyncMock) as m:
                m.return_value = (b'{"result": "ok"}', {}, 200)
                await client.chatgpt("hello", add_html=False)
            params = m.call_args[0][1]
            assert params["add_html"] == "false"

        asyncio.run(run())

    def test_chatgpt_country_code(self):
        async def run():
            from scrapingbee_cli.client import Client

            client = Client("fake-key")
            with patch.object(client, "_get_with_retry", new_callable=AsyncMock) as m:
                m.return_value = (b'{"result": "ok"}', {}, 200)
                await client.chatgpt("hello", country_code="gb")
            params = m.call_args[0][1]
            assert params["country_code"] == "gb"

        asyncio.run(run())

    def test_chatgpt_no_optional_params(self):
        """Only prompt sent when no optional params given."""

        async def run():
            from scrapingbee_cli.client import Client

            client = Client("fake-key")
            with patch.object(client, "_get_with_retry", new_callable=AsyncMock) as m:
                m.return_value = (b'{"result": "ok"}', {}, 200)
                await client.chatgpt("hello")
            params = m.call_args[0][1]
            assert params == {"prompt": "hello"}

        asyncio.run(run())


# =============================================================================
# 3. ensure_url_scheme
# =============================================================================


class TestEnsureUrlScheme:
    """Tests for ensure_url_scheme()."""

    def test_no_scheme_prepends_https(self):
        assert ensure_url_scheme("example.com") == "https://example.com"

    def test_with_path_prepends_https(self):
        assert ensure_url_scheme("example.com/page") == "https://example.com/page"

    def test_https_unchanged(self):
        assert ensure_url_scheme("https://example.com") == "https://example.com"

    def test_http_unchanged(self):
        assert ensure_url_scheme("http://example.com") == "http://example.com"

    def test_ftp_unchanged(self):
        assert ensure_url_scheme("ftp://files.example.com") == "ftp://files.example.com"

    def test_empty_string(self):
        assert ensure_url_scheme("") == ""

    def test_subdomain(self):
        assert ensure_url_scheme("docs.example.com/api") == "https://docs.example.com/api"

    def test_with_port(self):
        assert ensure_url_scheme("localhost:8080") == "https://localhost:8080"


# =============================================================================
# 4. _cli_allowed_domains (Scrapy attribute conflict fix)
# =============================================================================


class TestCliAllowedDomains:
    """Tests that crawl spider uses _cli_allowed_domains, not allowed_domains."""

    def test_spider_does_not_set_allowed_domains(self):
        """Scrapy's OffsiteMiddleware reads self.allowed_domains.
        Our spider must NOT set it, or ScrapingBee proxy requests get filtered."""
        from scrapingbee_cli.crawl import GenericScrapingBeeSpider

        spider = GenericScrapingBeeSpider(
            start_urls=["https://example.com"],
            allowed_domains=["example.com"],
        )
        # Scrapy's allowed_domains should be None/empty (not set by us)
        assert not hasattr(spider, "allowed_domains") or spider.allowed_domains is None

    def test_spider_stores_cli_allowed_domains(self):
        from scrapingbee_cli.crawl import GenericScrapingBeeSpider

        spider = GenericScrapingBeeSpider(
            start_urls=["https://example.com"],
            allowed_domains=["example.com", "other.com"],
        )
        assert spider._cli_allowed_domains == ["example.com", "other.com"]

    def test_url_allowed_with_cli_allowed_domains(self):
        from scrapingbee_cli.crawl import GenericScrapingBeeSpider

        spider = GenericScrapingBeeSpider(
            start_urls=["https://example.com"],
            allowed_domains=["example.com"],
        )
        assert spider._url_allowed("https://example.com/page") is True
        assert spider._url_allowed("https://other.com/page") is False

    def test_url_allowed_without_allowed_domains(self):
        """Without --allowed-domains, restricts to start URL domain."""
        from scrapingbee_cli.crawl import GenericScrapingBeeSpider

        spider = GenericScrapingBeeSpider(
            start_urls=["https://example.com"],
        )
        assert spider._url_allowed("https://example.com/page") is True
        assert spider._url_allowed("https://other.com/page") is False


# =============================================================================
# 5. Screenshot warning removed
# =============================================================================


class TestScreenshotWarning:
    """Tests that --screenshot-full-page without --screenshot produces no warning."""

    def test_no_warning_for_screenshot_full_page_alone(self):
        runner = CliRunner()
        with patch("scrapingbee_cli.commands.scrape.get_api_key", return_value="fake"):
            with patch("scrapingbee_cli.commands.scrape.asyncio") as mock_asyncio:
                mock_asyncio.run = lambda x: None
                from scrapingbee_cli.commands.scrape import scrape_cmd

                result = runner.invoke(
                    scrape_cmd,
                    ["https://example.com", "--screenshot-full-page", "true"],
                    obj={},
                    catch_exceptions=False,
                )
        # Should NOT contain the old warning
        assert "have no effect" not in (result.output or "")
        assert "have no effect" not in (result.stderr if hasattr(result, "stderr") else "")


# =============================================================================
# 6. Exact credit costs
# =============================================================================


class TestCreditCosts:
    """Tests for credits.py exact cost functions."""

    def test_google_light_default(self):
        assert google_credits() == 10
        assert google_credits(None) == 10

    def test_google_light_true(self):
        assert google_credits(True) == 10

    def test_google_light_false(self):
        assert google_credits(False) == 15

    def test_fast_search(self):
        assert fast_search_credits() == 10

    def test_amazon_light_default(self):
        assert amazon_credits() == 5
        assert amazon_credits(None) == 5

    def test_amazon_light_true(self):
        assert amazon_credits(True) == 5

    def test_amazon_light_false(self):
        assert amazon_credits(False) == 15

    def test_walmart_light_default(self):
        assert walmart_credits() == 10
        assert walmart_credits(None) == 10

    def test_walmart_light_false(self):
        assert walmart_credits(False) == 15

    def test_youtube(self):
        assert youtube_credits() == 5

    def test_chatgpt(self):
        assert chatgpt_credits() == 15

    def test_estimated_fallback_dict_exists(self):
        """ESTIMATED_CREDITS dict should exist as fallback."""
        assert "google" in ESTIMATED_CREDITS
        assert "fast-search" in ESTIMATED_CREDITS
        assert "chatgpt" in ESTIMATED_CREDITS


class TestWriteOutputCreditCost:
    """Tests that write_output uses credit_cost when provided."""

    def test_exact_cost_shown_when_provided(self, capsys):
        from scrapingbee_cli.cli_utils import write_output

        write_output(
            b"test",
            {},
            200,
            None,
            True,  # verbose
            command="google",
            credit_cost=10,
        )
        captured = capsys.readouterr()
        assert "Credit Cost: 10" in captured.err
        assert "estimated" not in captured.err

    def test_estimated_shown_when_no_credit_cost(self, capsys):
        from scrapingbee_cli.cli_utils import write_output

        write_output(
            b"test",
            {},
            200,
            None,
            True,  # verbose
            command="google",
        )
        captured = capsys.readouterr()
        assert "Credit Cost (estimated):" in captured.err

    def test_spb_cost_header_takes_precedence(self, capsys):
        from scrapingbee_cli.cli_utils import write_output

        write_output(
            b"test",
            {"spb-cost": "5"},
            200,
            None,
            True,  # verbose
            command="scrape",
            credit_cost=10,
        )
        captured = capsys.readouterr()
        assert "Credit Cost: 5" in captured.err
        # Should not show our credit_cost since header is present
        assert captured.err.count("Credit Cost") == 1


# =============================================================================
# 7. DepthMiddleware disabled
# =============================================================================


class TestDepthMiddlewareDisabled:
    """Tests that Scrapy's DepthMiddleware is disabled in crawl settings."""

    def test_depth_middleware_set_to_none(self):
        from scrapingbee_cli.crawl import _settings_with_scrapingbee

        settings = _settings_with_scrapingbee("fake-key")
        spider_mw = settings.get("SPIDER_MIDDLEWARES")
        assert "scrapy.spidermiddlewares.depth.DepthMiddleware" in spider_mw
        assert spider_mw["scrapy.spidermiddlewares.depth.DepthMiddleware"] is None


# =============================================================================
# ChatGPT CLI options appear in help
# =============================================================================


class TestChatGPTCLIOptions:
    """Tests that new ChatGPT CLI options are registered."""

    def test_chatgpt_help_shows_search(self):
        runner = CliRunner()
        from scrapingbee_cli.commands.chatgpt import chatgpt_cmd

        result = runner.invoke(chatgpt_cmd, ["--help"], obj={})
        assert "--search" in result.output

    def test_chatgpt_help_shows_add_html(self):
        runner = CliRunner()
        from scrapingbee_cli.commands.chatgpt import chatgpt_cmd

        result = runner.invoke(chatgpt_cmd, ["--help"], obj={})
        assert "--add-html" in result.output

    def test_chatgpt_help_shows_country_code(self):
        runner = CliRunner()
        from scrapingbee_cli.commands.chatgpt import chatgpt_cmd

        result = runner.invoke(chatgpt_cmd, ["--help"], obj={})
        assert "--country-code" in result.output
