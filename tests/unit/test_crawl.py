"""Unit tests for crawl module."""

from __future__ import annotations

from scrapingbee_cli.crawl import (
    _NON_HTML_URL_EXTENSIONS,
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


class TestSpiderDiscovery:
    """Tests for the double-fetch discovery mechanism in GenericScrapingBeeSpider."""

    def _make_response(self, url: str, body: bytes, depth: int = 0):
        """Create a Scrapy HtmlResponse with request meta attached."""
        from scrapy.http import HtmlResponse, Request

        response = HtmlResponse(url, body=body, encoding="utf-8")
        response.request = Request(url, meta={"depth": depth})
        return response

    def test_parse_yields_discovery_request_when_no_links(self):
        """parse() must yield exactly one discovery request when the body has no links."""
        from scrapy_scrapingbee import ScrapingBeeRequest

        from scrapingbee_cli.crawl import GenericScrapingBeeSpider

        spider = GenericScrapingBeeSpider(
            start_urls=["https://example.com"],
            scrape_params={"return_page_text": True},
            output_dir=None,
        )
        response = self._make_response("https://example.com/page", b"Plain text, no links")
        requests = list(spider.parse(response))

        assert len(requests) == 1
        assert isinstance(requests[0], ScrapingBeeRequest)
        assert requests[0].callback == spider._parse_discovery_links_only
        assert requests[0].dont_filter is True

    def test_parse_does_not_yield_discovery_when_links_found(self):
        """parse() must not yield a discovery request when the body already has links."""
        from scrapingbee_cli.crawl import GenericScrapingBeeSpider

        spider = GenericScrapingBeeSpider(
            start_urls=["https://example.com"],
            scrape_params={},
            output_dir=None,
        )
        spider.seen_urls.add("https://example.com")

        response = self._make_response(
            "https://example.com",
            b'<a href="/page1">link1</a><a href="/page2">link2</a>',
        )
        requests = list(spider.parse(response))

        # No request should target the discovery callback
        for req in requests:
            assert req.callback != spider._parse_discovery_links_only

    def test_parse_discovery_links_only_follows_links_but_does_not_save(self, tmp_path):
        """_parse_discovery_links_only must yield follow requests but never write files."""
        from scrapingbee_cli.crawl import GenericScrapingBeeSpider

        spider = GenericScrapingBeeSpider(
            start_urls=["https://example.com"],
            scrape_params={"return_page_text": True},
            output_dir=str(tmp_path),
        )
        spider.seen_urls.add("https://example.com")

        response = self._make_response(
            "https://example.com",
            b'<a href="/page1">p1</a><a href="/page2">p2</a>',
        )
        requests = list(spider._parse_discovery_links_only(response))

        # Should yield follow requests (not empty)
        assert len(requests) > 0
        # Each follow request must use the main parse callback (not discovery again)
        for req in requests:
            assert req.callback == spider.parse
        # Nothing written — discovery does not save
        assert list(tmp_path.iterdir()) == []


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


class TestNonHtmlUrlExtensions:
    """Tests for the _NON_HTML_URL_EXTENSIONS set and its use in parse()."""

    def test_image_extensions_are_binary(self):
        for ext in ("jpg", "jpeg", "png", "gif", "webp", "svg", "ico"):
            assert ext in _NON_HTML_URL_EXTENSIONS, f"{ext!r} should be in _NON_HTML_URL_EXTENSIONS"

    def test_download_extensions_are_binary(self):
        for ext in ("pdf", "zip"):
            assert ext in _NON_HTML_URL_EXTENSIONS

    def test_web_asset_extensions_are_binary(self):
        for ext in ("css", "js"):
            assert ext in _NON_HTML_URL_EXTENSIONS

    def test_html_like_extensions_not_in_set(self):
        # These can contain <a href> links and must NOT be skipped
        for ext in ("html", "htm", "asp", "aspx", "php", "xml", "md", "txt", "json"):
            assert ext not in _NON_HTML_URL_EXTENSIONS, (
                f"{ext!r} must not be in _NON_HTML_URL_EXTENSIONS"
            )

    def _make_response(self, url: str, body: bytes, depth: int = 0):
        from scrapy.http import HtmlResponse, Request

        response = HtmlResponse(url, body=body, encoding="utf-8")
        response.request = Request(url, meta={"depth": depth})
        return response

    def test_parse_skips_discovery_for_image_url(self):
        """parse() must NOT yield a discovery request when the URL is a known binary type."""
        from scrapingbee_cli.crawl import GenericScrapingBeeSpider

        spider = GenericScrapingBeeSpider(
            start_urls=["https://example.com"],
            scrape_params={"extract_rules": '{"price": ".price"}'},
            output_dir=None,
        )
        # Simulate fetching a JPEG URL that returns no links (binary body)
        response = self._make_response(
            "https://example.com/hero.jpg",
            b"\xff\xd8\xff\xe0",  # JPEG magic bytes
        )
        requests = list(spider.parse(response))
        # Must yield nothing — no discovery re-request for binary URLs
        assert requests == [], f"Expected no requests for binary URL, got {requests}"

    def test_parse_still_fires_discovery_for_html_url_with_no_links(self):
        """parse() must still yield a discovery request for HTML-like URLs with no links."""
        from scrapy_scrapingbee import ScrapingBeeRequest

        from scrapingbee_cli.crawl import GenericScrapingBeeSpider

        spider = GenericScrapingBeeSpider(
            start_urls=["https://example.com"],
            scrape_params={"extract_rules": '{"price": ".price"}'},
            output_dir=None,
        )
        # JSON response body (from extract_rules) has no links
        response = self._make_response(
            "https://example.com/product",  # no binary extension → should fire discovery
            b'{"price": "$9.99"}',
        )
        requests = list(spider.parse(response))
        assert len(requests) == 1
        assert isinstance(requests[0], ScrapingBeeRequest)
        assert requests[0].callback == spider._parse_discovery_links_only

    def test_parse_skips_discovery_for_css_url(self):
        """CSS files never contain HTML links — discovery must be skipped."""
        from scrapingbee_cli.crawl import GenericScrapingBeeSpider

        spider = GenericScrapingBeeSpider(
            start_urls=["https://example.com"],
            scrape_params={},
            output_dir=None,
        )
        response = self._make_response(
            "https://example.com/styles/main.css",
            b"body { color: red; }",
        )
        requests = list(spider.parse(response))
        assert requests == []


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
