"""Unit tests for crawl module."""

from __future__ import annotations

import pytest

from scrapingbee_cli.crawl import (
    _body_from_json_response,
    _extract_hrefs_from_body,
    _extract_hrefs_from_response,
    _needs_discovery_phase,
    _normalize_url,
    _param_truthy,
    _params_for_discovery,
    _preferred_extension_from_scrape_params,
    default_crawl_output_dir,
)


class TestNormalizeUrl:
    """Tests for _normalize_url()."""

    def test_strips_fragment(self):
        assert _normalize_url("https://example.com/page#section") == "https://example.com/page"

    def test_strips_trailing_slash(self):
        assert _normalize_url("https://example.com/") == "https://example.com/"

    def test_preserves_query(self):
        # Path is normalized to / when empty, so query attaches after /
        assert _normalize_url("https://example.com?a=1") == "https://example.com/?a=1"


class TestParamTruthy:
    """Tests for _param_truthy()."""

    def test_true_value(self):
        assert _param_truthy({"a": True}, "a") is True
        assert _param_truthy({"a": "true"}, "a") is True
        assert _param_truthy({"a": "True"}, "a") is True  # case-insensitive
        assert _param_truthy({"a": "1"}, "a") is True
        assert _param_truthy({"a": "yes"}, "a") is True

    def test_false_value(self):
        assert _param_truthy({"a": False}, "a") is False
        assert _param_truthy({"a": "false"}, "a") is False
        assert _param_truthy({"a": None}, "a") is False
        assert _param_truthy({}, "a") is False


class TestNeedsDiscoveryPhase:
    """Tests for _needs_discovery_phase()."""

    def test_return_text_always_discovery(self):
        assert _needs_discovery_phase({"return_page_text": True}) is True
        assert _needs_discovery_phase({"return_page_text": "true"}) is True

    def test_screenshot_without_json_response_discovery(self):
        assert _needs_discovery_phase({"screenshot": True, "json_response": False}) is True
        assert _needs_discovery_phase({"screenshot": True}) is True

    def test_screenshot_with_json_response_no_discovery(self):
        assert _needs_discovery_phase({"screenshot": True, "json_response": True}) is False

    def test_no_special_params_no_discovery(self):
        assert _needs_discovery_phase({}) is False
        assert _needs_discovery_phase({"json_response": True}) is False


class TestParamsForDiscovery:
    """Tests for _params_for_discovery()."""

    def test_strips_screenshot_and_return_text(self):
        params = {"screenshot": True, "return_page_text": True, "render_js": True}
        out = _params_for_discovery(params)
        assert "screenshot" not in out
        assert "return_page_text" not in out
        assert out.get("render_js") is True

    def test_strips_json_response(self):
        params = {"json_response": True, "wait": 1000}
        out = _params_for_discovery(params)
        assert "json_response" not in out
        assert out.get("wait") == 1000


class TestPreferredExtensionFromScrapeParams:
    """Tests for _preferred_extension_from_scrape_params()."""

    def test_screenshot_and_json_response(self):
        assert _preferred_extension_from_scrape_params({"screenshot": True, "json_response": True}) == "json"

    def test_screenshot_only(self):
        assert _preferred_extension_from_scrape_params({"screenshot": True}) == "png"

    def test_return_markdown(self):
        assert _preferred_extension_from_scrape_params({"return_page_markdown": True}) == "md"

    def test_return_text(self):
        assert _preferred_extension_from_scrape_params({"return_page_text": True}) == "txt"

    def test_json_response_only(self):
        assert _preferred_extension_from_scrape_params({"json_response": True}) == "json"

    def test_none_when_no_match(self):
        assert _preferred_extension_from_scrape_params({}) is None


class TestBodyFromJsonResponse:
    """Tests for _body_from_json_response()."""

    def test_returns_body_field(self):
        body = b'{"body": "<html>hi</html>", "other": 1}'
        assert _body_from_json_response(body) == b"<html>hi</html>"

    def test_returns_content_field_when_no_body(self):
        body = b'{"content": "markdown here"}'
        assert _body_from_json_response(body) == b"markdown here"

    def test_returns_none_for_non_json(self):
        assert _body_from_json_response(b"<html/>") is None
        assert _body_from_json_response(b"[Crawler](/)") is None

    def test_returns_none_for_empty(self):
        assert _body_from_json_response(b"") is None


class TestExtractHrefsFromBody:
    """Tests for _extract_hrefs_from_body()."""

    def test_html_href(self):
        body = b'<a href="/page">link</a>'
        assert _extract_hrefs_from_body(body) == ["/page"]

    def test_markdown_links(self):
        body = b"[text](/path) and [other](https://example.com/other)"
        assert "/path" in _extract_hrefs_from_body(body)
        assert "https://example.com/other" in _extract_hrefs_from_body(body)

    def test_extracts_mailto_and_anchor_hrefs(self):
        # _extract_hrefs_from_body returns all hrefs; spider filters #/mailto:/javascript: later
        body = b'<a href="mailto:x@y.com">m</a><a href="#anchor">a</a>'
        hrefs = _extract_hrefs_from_body(body)
        assert "mailto:x@y.com" in hrefs
        assert "#anchor" in hrefs


class TestExtractHrefsFromResponse:
    """Tests for _extract_hrefs_from_response()."""

    def test_json_body_extraction(self):
        from scrapy.http import HtmlResponse

        # Response with JSON body containing HTML in "body" field
        body = b'{"body": "<a href=\\"https://example.com/page\\">link</a>"}'
        response = HtmlResponse("https://example.com", body=body)
        hrefs = _extract_hrefs_from_response(response)
        assert "https://example.com/page" in hrefs or "/page" in hrefs

    def test_html_links_via_css(self):
        from scrapy.http import HtmlResponse

        body = b'<html><a href="/foo">x</a><a href="https://other.com/b">y</a></html>'
        response = HtmlResponse("https://example.com", body=body)
        hrefs = _extract_hrefs_from_response(response)
        assert "/foo" in hrefs
        assert "https://other.com/b" in hrefs


class TestDefaultCrawlOutputDir:
    """Tests for default_crawl_output_dir()."""

    def test_format(self):
        name = default_crawl_output_dir()
        assert name.startswith("crawl_")
        rest = name.replace("crawl_", "")
        assert len(rest) == 15  # YYYYMMDD_HHMMSS
        assert rest[8] == "_"
