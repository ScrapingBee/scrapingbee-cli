"""Unit tests for crawl module."""

from __future__ import annotations

from scrapingbee_cli.crawl import (
    _body_from_json_response,
    _extract_hrefs_from_body,
    _extract_hrefs_from_response,
    _normalize_url,
    _param_truthy,
    _params_for_discovery,
    _preferred_extension_from_scrape_params,
    _requires_discovery_phase,
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

    def test_strips_ai_params(self):
        params = {
            "ai_query": "extract links",
            "ai_selector": "a",
            "ai_extract_rules": "{}",
            "wait": 500,
        }
        out = _params_for_discovery(params)
        assert "ai_query" not in out
        assert "ai_selector" not in out
        assert "ai_extract_rules" not in out
        assert out.get("wait") == 500

    def test_strips_extract_rules(self):
        params = {"extract_rules": '{"title": "h1"}', "render_js": True}
        out = _params_for_discovery(params)
        assert "extract_rules" not in out
        assert out.get("render_js") is True


class TestPreferredExtensionFromScrapeParams:
    """Tests for _preferred_extension_from_scrape_params()."""

    def test_screenshot_and_json_response(self):
        assert (
            _preferred_extension_from_scrape_params({"screenshot": True, "json_response": True})
            == "json"
        )

    def test_screenshot_only(self):
        assert _preferred_extension_from_scrape_params({"screenshot": True}) == "png"

    def test_screenshot_full_page_only(self):
        # Regression (C1): full-page screenshots must map to .png, not .html.
        assert _preferred_extension_from_scrape_params({"screenshot_full_page": True}) == "png"

    def test_screenshot_selector_only(self):
        assert _preferred_extension_from_scrape_params({"screenshot_selector": "#main"}) == "png"

    def test_screenshot_full_page_with_json_response(self):
        assert (
            _preferred_extension_from_scrape_params(
                {"screenshot_full_page": "true", "json_response": True}
            )
            == "json"
        )

    def test_return_markdown(self):
        assert _preferred_extension_from_scrape_params({"return_page_markdown": True}) == "md"

    def test_return_text(self):
        assert _preferred_extension_from_scrape_params({"return_page_text": True}) == "txt"

    def test_json_response_only(self):
        assert _preferred_extension_from_scrape_params({"json_response": True}) == "json"

    def test_extract_rules(self):
        assert (
            _preferred_extension_from_scrape_params({"extract_rules": '{"title": "h1"}'}) == "json"
        )

    def test_ai_extract_rules(self):
        assert (
            _preferred_extension_from_scrape_params({"ai_extract_rules": '{"title": "h1"}'})
            == "json"
        )

    def test_ai_query(self):
        assert _preferred_extension_from_scrape_params({"ai_query": "What is the price?"}) == "json"

    def test_ai_selector_alone_returns_none(self):
        # ai_selector is a modifier for ai_query/ai_extract_rules, not a JSON producer on its own.
        assert _preferred_extension_from_scrape_params({"ai_selector": "h1"}) is None

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


class TestSpiderSaveResponse:
    """Tests for _save_response manifest field extraction."""

    def _make_spider(self, tmp_path):
        from scrapingbee_cli.crawl import GenericScrapingBeeSpider

        return GenericScrapingBeeSpider(
            start_urls=["https://example.com"],
            scrape_params={},
            output_dir=str(tmp_path),
        )

    def _make_response(self, url, body, headers=None, meta=None):
        import scrapy

        return scrapy.http.TextResponse(
            url=url,
            body=body,
            encoding="utf-8",
            headers=headers or {},
            request=scrapy.Request(url, meta=meta or {}),
        )

    def test_save_response_extracts_credits_used(self, tmp_path):
        spider = self._make_spider(tmp_path)
        response = self._make_response(
            "https://example.com/page",
            b"<html>test</html>",
            headers={"Spb-Cost": "5"},
        )
        spider._save_response(response)
        entry = spider._url_file_map["https://example.com/page"]
        assert entry["credits_used"] == 5

    def test_save_response_credits_none_when_no_header(self, tmp_path):
        spider = self._make_spider(tmp_path)
        response = self._make_response(
            "https://example.com/page",
            b"<html>test</html>",
        )
        spider._save_response(response)
        entry = spider._url_file_map["https://example.com/page"]
        assert entry["credits_used"] is None

    def test_save_response_extracts_latency_ms(self, tmp_path):
        spider = self._make_spider(tmp_path)
        response = self._make_response(
            "https://example.com/page",
            b"<html>test</html>",
            meta={"download_latency": 1.5},
        )
        spider._save_response(response)
        entry = spider._url_file_map["https://example.com/page"]
        assert entry["latency_ms"] == 1500

    def test_save_response_latency_none_when_no_meta(self, tmp_path):
        spider = self._make_spider(tmp_path)
        response = self._make_response(
            "https://example.com/page",
            b"<html>test</html>",
        )
        spider._save_response(response)
        entry = spider._url_file_map["https://example.com/page"]
        assert entry["latency_ms"] is None

    def test_save_response_writes_file(self, tmp_path):
        spider = self._make_spider(tmp_path)
        response = self._make_response(
            "https://example.com/page",
            b"<html>test</html>",
        )
        spider._save_response(response)
        assert (tmp_path / "1.html").exists()
        assert (tmp_path / "1.html").read_bytes() == b"<html>test</html>"

    def test_save_response_manifest_has_required_fields(self, tmp_path):
        spider = self._make_spider(tmp_path)
        response = self._make_response(
            "https://example.com/page",
            b"<html>test</html>",
            headers={"Spb-Cost": "10"},
            meta={"download_latency": 0.5},
        )
        spider._save_response(response)
        entry = spider._url_file_map["https://example.com/page"]
        for field in ("file", "fetched_at", "http_status", "credits_used", "latency_ms"):
            assert field in entry, f"Missing field {field!r}"

    def test_save_response_extract_rules_writes_json_for_html_url(self, tmp_path):
        """SCR-371: with --extract-rules, JSON body must be saved as .json
        even when the URL path ends with .html (URL heuristic must not win)."""
        from scrapingbee_cli.crawl import GenericScrapingBeeSpider

        spider = GenericScrapingBeeSpider(
            start_urls=["https://books.toscrape.com/"],
            scrape_params={"extract_rules": '{"title": "h1", "price": ".price_color"}'},
            output_dir=str(tmp_path),
        )
        response = self._make_response(
            "https://books.toscrape.com/catalogue/libertarianism-for-beginners_982/index.html",
            b'{"title": "Libertarianism for Beginners", "price": "\\u00a351.33"}',
        )
        spider._save_response(response)
        assert (tmp_path / "1.json").exists(), "Expected 1.json (JSON body), not .html"
        assert not (tmp_path / "1.html").exists(), "Must not save JSON body as .html"
        url = "https://books.toscrape.com/catalogue/libertarianism-for-beginners_982/index.html"
        assert spider._url_file_map[url]["file"] == "1.json"

    def test_save_response_ai_query_writes_json_for_html_url(self, tmp_path):
        """SCR-371: --ai-query also forces JSON extension regardless of URL path."""
        from scrapingbee_cli.crawl import GenericScrapingBeeSpider

        spider = GenericScrapingBeeSpider(
            start_urls=["https://example.com/"],
            scrape_params={"ai_query": "What is the price?"},
            output_dir=str(tmp_path),
        )
        response = self._make_response(
            "https://example.com/products/widget.html",
            b'{"answer": "$9.99"}',
        )
        spider._save_response(response)
        assert (tmp_path / "1.json").exists()
        assert not (tmp_path / "1.html").exists()


class TestRequiresDiscoveryPhase:
    """Tests for _requires_discovery_phase()."""

    def test_extract_rules_requires_discovery(self):
        assert _requires_discovery_phase({"extract_rules": '{"price": ".price"}'}) is True

    def test_ai_extract_rules_requires_discovery(self):
        assert _requires_discovery_phase({"ai_extract_rules": '{"title": "h1"}'}) is True

    def test_ai_query_requires_discovery(self):
        assert _requires_discovery_phase({"ai_query": "What is the main heading?"}) is True

    def test_return_page_text_requires_discovery(self):
        assert _requires_discovery_phase({"return_page_text": "true"}) is True

    def test_screenshot_without_json_response_requires_discovery(self):
        assert _requires_discovery_phase({"screenshot": "true"}) is True

    def test_screenshot_with_json_response_does_not_require_discovery(self):
        # json_response wraps the HTML body — links can be extracted from it
        assert _requires_discovery_phase({"screenshot": "true", "json_response": "true"}) is False

    def test_plain_render_js_does_not_require_discovery(self):
        assert _requires_discovery_phase({"render_js": "true"}) is False

    def test_json_response_alone_does_not_require_discovery(self):
        # json_response wraps HTML body field — still linkable
        assert _requires_discovery_phase({"json_response": "true"}) is False

    def test_empty_params_does_not_require_discovery(self):
        assert _requires_discovery_phase({}) is False

    def test_return_page_markdown_does_not_require_discovery(self):
        # Markdown responses are handled by _MARKDOWN_LINK_RE — no discovery needed if links present
        assert _requires_discovery_phase({"return_page_markdown": "true"}) is False


class TestExtractHrefsExceptionHandling:
    """Tests that _extract_hrefs_from_response handles non-HTML gracefully."""

    def _make_response(self, url: str, body: bytes):
        from scrapy.http import HtmlResponse, Request

        response = HtmlResponse(url, body=body, encoding="utf-8")
        response.request = Request(url, meta={"depth": 0})
        return response

    def test_binary_body_returns_empty_list(self):
        """Binary bodies (images, PDFs) must return [] without raising."""
        response = self._make_response(
            "https://example.com/photo.jpg",
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",  # PNG magic bytes
        )
        result = _extract_hrefs_from_response(response)
        assert isinstance(result, list)

    def test_json_extract_rules_body_returns_empty_list(self):
        """JSON from extract_rules has no HTML links — must return []."""
        response = self._make_response(
            "https://example.com/product",
            b'{"price": "$9.99", "title": "Widget"}',
        )
        result = _extract_hrefs_from_response(response)
        assert result == []

    def test_plain_text_body_returns_empty_list(self):
        """Plain text from return_page_text has no links — must return []."""
        response = self._make_response(
            "https://example.com/page",
            b"This is just plain text with no links.",
        )
        result = _extract_hrefs_from_response(response)
        assert result == []


class TestDefaultCrawlOutputDir:
    """Tests for default_crawl_output_dir()."""

    def test_format(self):
        name = default_crawl_output_dir()
        assert name.startswith("crawl_")
        rest = name.replace("crawl_", "")
        assert len(rest) == 15  # YYYYMMDD_HHMMSS
        assert rest[8] == "_"


class TestMaxPagesHardCap:
    """`--max-pages N` must be a hard cap on saved files regardless of crawl
    concurrency (report C1/M3): responses already in flight when the cap trips
    must be dropped, not written. Enforced centrally in _save_response."""

    def _spider(self, tmp_path, max_pages):
        from scrapingbee_cli.crawl import GenericScrapingBeeSpider

        return GenericScrapingBeeSpider(
            start_urls=["http://example.com"],
            scrape_params={},
            output_dir=str(tmp_path),
            max_pages=max_pages,
            name="t",
        )

    def _resp(self, url):
        from scrapy.http import Request, Response

        return Response(url=url, body=b"data", status=200, headers={}, request=Request(url=url))

    def test_overshoot_is_dropped(self, tmp_path):
        sp = self._spider(tmp_path, 2)
        assert sp._save_response(self._resp("http://example.com/a")) is True
        assert sp._save_response(self._resp("http://example.com/b")) is True
        # A response that was already in flight when the cap tripped
        # (concurrency > 1) — must be dropped, not written.
        assert sp._save_response(self._resp("http://example.com/c")) is False
        assert sp._save_count == 2
        written = [p for p in tmp_path.rglob("*") if p.is_file()]
        assert len(written) == 2

    def test_zero_means_unlimited(self, tmp_path):
        sp = self._spider(tmp_path, 0)
        for i in range(4):
            assert sp._save_response(self._resp(f"http://example.com/{i}")) is True
        assert sp._save_count == 4
