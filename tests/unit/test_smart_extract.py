"""Comprehensive tests for path language and smart-extract features."""

from __future__ import annotations

import json

from scrapingbee_cli.cli_utils import (
    _build_matcher,
    _parse_field_blocks,
    _parse_path,
    _resolve_path,
    resolve_expression,
)
from scrapingbee_cli.extract import (
    _auto_parse,
    smart_extract,
)

# ── TestParsePath ────────────────────────────────────────────────────────────


class TestParsePath:
    """Parser produces correct typed segments."""

    def test_simple_dot_path(self):
        assert _parse_path("a.b.c") == [("key", "a"), ("key", "b"), ("key", "c")]

    def test_escaped_key(self):
        assert _parse_path("(a.b).c") == [("key", "a.b"), ("key", "c")]

    def test_index_zero(self):
        assert _parse_path("[0]") == [("index", 0)]

    def test_negative_index(self):
        assert _parse_path("[-1]") == [("index", -1)]

    def test_slice(self):
        assert _parse_path("[0:5]") == [("slice", (0, 5))]

    def test_multi_index(self):
        assert _parse_path("[0,3,7]") == [("multi_index", [0, 3, 7])]

    def test_keys_operation(self):
        assert _parse_path("[keys]") == [("keys", None)]

    def test_values_operation(self):
        assert _parse_path("[values]") == [("values", None)]

    def test_recursive_search(self):
        segs = _parse_path("...key")
        assert len(segs) == 1
        assert segs[0][0] == "recurse"
        assert segs[0][1] == ("key", 0)

    def test_recursive_glob(self):
        segs = _parse_path("...*glob*")
        assert segs[0] == ("recurse", ("*glob*", 0))

    def test_recursive_escaped(self):
        segs = _parse_path("...(escaped)")
        assert segs[0] == ("recurse", ("escaped", 0))

    def test_recursive_with_context(self):
        segs = _parse_path("...key~3")
        assert segs[0] == ("recurse", ("key", 3))

    def test_value_filter_glob(self):
        assert _parse_path("[=*pattern*]") == [("filter_value", "*pattern*")]

    def test_value_filter_regex(self):
        assert _parse_path("[=/regex/]") == [("filter_value", "/regex/")]

    def test_key_filter(self):
        assert _parse_path("[key=*pattern*]") == [("filter_key", ("key", "*pattern*"))]

    def test_combined_path(self):
        segs = _parse_path("xhr[0].body.paths[keys][0:5]")
        assert segs == [
            ("key", "xhr"),
            ("index", 0),
            ("key", "body"),
            ("key", "paths"),
            ("keys", None),
            ("slice", (0, 5)),
        ]


# ── TestResolvePath ──────────────────────────────────────────────────────────


class TestResolvePath:
    """Resolver works correctly for various path operations."""

    def test_dict_key_navigation(self):
        obj = {"a": {"b": {"c": 42}}}
        assert _resolve_path(obj, _parse_path("a.b.c")) == 42

    def test_list_indexing(self):
        obj = {"items": [10, 20, 30]}
        assert _resolve_path(obj, _parse_path("items[0]")) == 10

    def test_list_negative_index(self):
        obj = {"items": [10, 20, 30]}
        assert _resolve_path(obj, _parse_path("items[-1]")) == 30

    def test_list_slicing(self):
        obj = {"items": [10, 20, 30, 40, 50]}
        assert _resolve_path(obj, _parse_path("items[0:3]")) == [10, 20, 30]

    def test_multi_index(self):
        obj = {"items": ["a", "b", "c", "d", "e", "f", "g", "h"]}
        assert _resolve_path(obj, _parse_path("items[0,3,7]")) == ["a", "d", "h"]

    def test_keys_on_dict(self):
        obj = {"x": 1, "y": 2}
        result = _resolve_path(obj, _parse_path("[keys]"))
        assert result == ["x", "y"]

    def test_values_on_dict(self):
        obj = {"x": 1, "y": 2}
        assert _resolve_path(obj, _parse_path("[values]")) == [1, 2]

    def test_keys_on_list_of_dicts(self):
        obj = {"items": [{"a": 1}, {"b": 2}]}
        result = _resolve_path(obj, _parse_path("items[keys]"))
        assert result == ["a", "b"]

    def test_json_string_auto_parse(self):
        obj = {"body": '{"name": "Alice"}'}
        assert _resolve_path(obj, _parse_path("body.name")) == "Alice"

    def test_recursive_search(self):
        obj = {"a": {"b": {"target": 99}}}
        result = _resolve_path(obj, _parse_path("...target"))
        assert result == [99]

    def test_recursive_glob(self):
        obj = {"user_email": "a@b.com", "nested": {"admin_email": "c@d.com"}}
        result = _resolve_path(obj, _parse_path("...*email*"))
        assert "a@b.com" in result
        assert "c@d.com" in result

    def test_context_expansion_tilde1(self):
        obj = {"items": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]}
        result = _resolve_path(obj, _parse_path("...name~1"))
        # ~1 returns the parent dict containing "name"
        assert len(result) == 2
        assert result[0] == {"id": 1, "name": "Alice"}

    def test_context_expansion_tilde2(self):
        obj = {"data": {"items": [{"id": 1, "name": "Alice"}]}}
        result = _resolve_path(obj, _parse_path("...name~2"))
        # ~2 returns grandparent
        assert len(result) == 1

    def test_value_filter_substring(self):
        obj = {"urls": ["https://example.com", "https://google.com", "ftp://server"]}
        result = _resolve_path(obj, _parse_path("urls[=*google*]"))
        assert result == ["https://google.com"]

    def test_value_filter_regex(self):
        obj = {"urls": ["https://example.com", "http://test.org", "ftp://server"]}
        result = _resolve_path(obj, _parse_path("urls[=/^https/]"))
        assert result == ["https://example.com"]

    def test_key_filter(self):
        obj = {"items": [{"type": "book", "title": "X"}, {"type": "dvd", "title": "Y"}]}
        result = _resolve_path(obj, _parse_path("items[type=book]"))
        assert result == [{"type": "book", "title": "X"}]

    def test_per_item_mapping(self):
        obj = {"items": [{"tags": ["a", "b"]}, {"tags": ["c", "d"]}]}
        result = _resolve_path(obj, _parse_path("items.tags[0]"))
        assert result == ["a", "c"]

    def test_missing_key_returns_none(self):
        obj = {"a": 1}
        assert _resolve_path(obj, _parse_path("b")) is None

    def test_index_out_of_range_returns_none(self):
        obj = {"items": [1]}
        assert _resolve_path(obj, _parse_path("items[5]")) is None


# ── TestBuildMatcher ─────────────────────────────────────────────────────────


class TestBuildMatcher:
    """Three matcher modes plus graceful fallback."""

    def test_substring_match(self):
        m = _build_matcher("hello")
        assert m("say hello world") is True
        assert m("goodbye") is False

    def test_glob_match(self):
        m = _build_matcher("*pattern*")
        assert m("some_pattern_here") is True
        assert m("nope") is False

    def test_regex_match(self):
        m = _build_matcher("/^https?://.*\\.com$/")
        assert m("https://example.com") is True
        assert m("ftp://example.com") is False

    def test_invalid_regex_fallback(self):
        m = _build_matcher("/[invalid/")
        # Should return a matcher that always returns False
        assert m("anything") is False


# ── TestResolveExpression ────────────────────────────────────────────────────


class TestResolveExpression:
    """Operators: single path, OR, AND, mixed error."""

    def test_single_path(self):
        obj = {"a": {"b": 1}}
        assert resolve_expression(obj, "a.b") == 1

    def test_or_operator(self):
        obj = {"x": 10, "y": 20}
        result = resolve_expression(obj, "x | y")
        assert result == [10, 20]

    def test_or_with_missing_part(self):
        obj = {"x": 10}
        result = resolve_expression(obj, "x | z")
        assert result == [10]

    def test_and_operator(self):
        obj = {"x": 10, "y": 20}
        result = resolve_expression(obj, "x & y")
        assert result == [10, 20]

    def test_and_fail_when_missing(self):
        obj = {"x": 10}
        result = resolve_expression(obj, "x & missing")
        assert result is None

    def test_mixed_or_and_error(self):
        obj = {"x": 1}
        result = resolve_expression(obj, "a | b & c")
        assert result is None

    def test_value_filter_in_or(self):
        obj = {"urls": ["https://a.com", "ftp://b"], "names": ["Alice"]}
        result = resolve_expression(obj, "urls[=*https*] | names")
        assert "https://a.com" in result
        assert "Alice" in result


# ── TestParseFieldBlocks ─────────────────────────────────────────────────────


class TestParseFieldBlocks:
    """Field block parser for old and new formats."""

    def test_old_format(self):
        result = _parse_field_blocks("title,price")
        assert result == [("title", "title"), ("price", "price")]

    def test_new_format(self):
        result = _parse_field_blocks("{title},{price}")
        assert result == [("title", "title"), ("price", "price")]

    def test_named_blocks(self):
        result = _parse_field_blocks("{book:title},{cost:price}")
        assert result == [("book", "title"), ("cost", "price")]

    def test_colon_in_slice(self):
        result = _parse_field_blocks("{first5:paths[keys][0:5]}")
        assert result == [("first5", "paths[keys][0:5]")]

    def test_auto_name_derivation(self):
        result = _parse_field_blocks("{info.title}")
        assert result[0][0] == "title"
        assert result[0][1] == "info.title"

    def test_commas_in_escaped_keys(self):
        result = _parse_field_blocks("{val:(a,b).c},{other:d}")
        assert result == [("val", "(a,b).c"), ("other", "d")]

    def test_empty_string(self):
        assert _parse_field_blocks("") == []


# ── TestAutoDetect ───────────────────────────────────────────────────────────


class TestAutoDetect:
    """Format auto-detection."""

    def test_json_object(self):
        data = b'{"key": "value"}'
        result = _auto_parse(data)
        assert result == {"key": "value"}

    def test_json_array(self):
        data = b"[1, 2, 3]"
        result = _auto_parse(data)
        assert result == [1, 2, 3]

    def test_html(self):
        data = b"<html><body><p>Hello</p></body></html>"
        result = _auto_parse(data)
        assert result is not None
        assert isinstance(result, (dict, str))

    def test_xml(self):
        data = b'<?xml version="1.0"?><root><item>test</item></root>'
        result = _auto_parse(data)
        assert result is not None

    def test_csv(self):
        data = b"name,age\nAlice,30\nBob,25"
        result = _auto_parse(data)
        assert isinstance(result, list)
        assert result[0]["name"] == "Alice"
        assert result[0]["age"] == "30"

    def test_plain_text_fallback(self):
        data = b"Just some plain text\nwith multiple lines"
        result = _auto_parse(data)
        assert isinstance(result, list)
        assert result[0] == "Just some plain text"

    def test_markdown_with_headings(self):
        data = b"# Title\nSome text\n## Section\nMore text"
        result = _auto_parse(data)
        assert isinstance(result, dict)
        assert "Title" in result

    def test_empty_data(self):
        assert _auto_parse(b"") is None
        assert _auto_parse(b"   ") is None


# ── TestSmartExtract ─────────────────────────────────────────────────────────


class TestSmartExtract:
    """End-to-end smart_extract tests."""

    def test_json_single_path(self):
        data = json.dumps({"users": [{"name": "Alice"}, {"name": "Bob"}]}).encode()
        result = smart_extract(data, "users.name")
        lines = result.decode().strip().split("\n")
        assert "Alice" in lines
        assert "Bob" in lines

    def test_json_schema_mode(self):
        data = json.dumps({"title": "Test", "price": 9.99}).encode()
        expression = '{"t": "title", "p": "price"}'
        result = json.loads(smart_extract(data, expression))
        assert result["t"] == "Test"
        assert result["p"] == 9.99

    def test_json_block_syntax(self):
        data = json.dumps({"title": "Test", "price": 9.99}).encode()
        result = json.loads(smart_extract(data, "{t:title},{p:price}"))
        assert result["t"] == "Test"
        assert result["p"] == 9.99

    def test_html_recursive_search(self):
        html = b"<html><body><a href='http://example.com'>Link</a></body></html>"
        result = smart_extract(html, "...href")
        assert b"http://example.com" in result

    def test_csv_column_access(self):
        csv_data = b"name,age\nAlice,30\nBob,25"
        result = smart_extract(csv_data, "name")
        text = result.decode().strip()
        assert "Alice" in text
        assert "Bob" in text

    def test_no_match_returns_empty(self):
        data = json.dumps({"a": 1}).encode()
        result = smart_extract(data, "nonexistent")
        assert result == b""


# ── TestChaining ────────────────────────────────────────────────────────────


# Complex test data simulating an e-commerce page
_SHOP = {
    "body": {
        "nav": {
            "class": "sidebar",
            "a": [
                {"href": "/home", "text": "Home"},
                {"href": "/about", "text": "About"},
            ],
        },
        "main": {
            "id": "products",
            "section": [
                {
                    "class": "product",
                    "h2": "Widget",
                    "span": {"class": "price", "text": "$49.99"},
                    "ul": {
                        "li": [
                            {"class": "tag", "text": "sale"},
                            {"class": "tag", "text": "popular"},
                        ]
                    },
                },
                {
                    "class": "product",
                    "h2": "Gadget",
                    "span": {"class": "price", "text": "$99.50"},
                    "ul": {
                        "li": [
                            {"class": "tag", "text": "new"},
                        ]
                    },
                },
                {
                    "class": "featured",
                    "h2": "Deluxe",
                    "span": {"class": "price", "text": "$249.00"},
                    "ul": {
                        "li": [
                            {"class": "tag", "text": "premium"},
                            {"class": "tag", "text": "sale"},
                        ]
                    },
                },
            ],
        },
        "footer": {
            "text": "Copyright 2024",
            "a": {"href": "mailto:shop@example.com", "text": "shop@example.com"},
        },
    },
}

# Nested JSON string data (simulates --json-response xhr)
_XHR = {
    "xhr": [
        {
            "url": "https://api.example.com/data.json",
            "body": json.dumps(
                {
                    "info": {"title": "Shop API", "version": "2.0"},
                    "endpoints": {
                        "/products": {
                            "get": {"summary": "List products"},
                            "post": {"summary": "Create product"},
                        },
                        "/orders": {"get": {"summary": "List orders"}},
                        "/users": {
                            "get": {"summary": "List users"},
                            "delete": {"summary": "Remove user"},
                        },
                    },
                }
            ),
        }
    ],
}


class TestChaining:
    """Complex chaining scenarios covering every operation combination."""

    # ── Navigate + Select ────────────────────────────────────────────────

    def test_key_then_index(self):
        r = _resolve_path(_SHOP, _parse_path("body.main.section[0].h2"))
        assert r == "Widget"

    def test_key_then_slice(self):
        r = _resolve_path(_SHOP, _parse_path("body.main.section[0:2].h2"))
        assert r == ["Widget", "Gadget"]

    def test_key_then_multi_index(self):
        r = _resolve_path(_SHOP, _parse_path("body.main.section[0,2].h2"))
        assert r == ["Widget", "Deluxe"]

    def test_key_then_negative_index(self):
        r = _resolve_path(_SHOP, _parse_path("body.main.section[-1].h2"))
        assert r == "Deluxe"

    # ── Navigate + [keys] / [values] ─────────────────────────────────────

    def test_keys_on_nested_dict(self):
        r = _resolve_path(_SHOP, _parse_path("body[keys]"))
        assert r == ["nav", "main", "footer"]

    def test_values_then_keys(self):
        r = _resolve_path(_XHR, _parse_path("xhr.body.endpoints[values][keys]"))
        assert "get" in r
        assert "post" in r
        assert "delete" in r

    def test_keys_then_slice(self):
        r = _resolve_path(_XHR, _parse_path("xhr.body.endpoints[keys][0:2]"))
        assert r == ["/products", "/orders"]

    def test_keys_then_multi_index(self):
        r = _resolve_path(_XHR, _parse_path("xhr.body.endpoints[keys][0,-1]"))
        assert r == ["/products", "/users"]

    # ── Recursive search + chaining ──────────────────────────────────────

    def test_recursive_then_key(self):
        r = _resolve_path(_SHOP, _parse_path("...section.h2"))
        assert "Widget" in r
        assert "Gadget" in r
        assert "Deluxe" in r

    def test_recursive_then_index(self):
        r = _resolve_path(_SHOP, _parse_path("...section[0].h2"))
        assert r == "Widget"  # [0] selects single item, .h2 returns scalar

    def test_recursive_then_keys(self):
        r = _resolve_path(_XHR, _parse_path("...endpoints[keys]"))
        assert "/products" in r
        assert "/orders" in r

    def test_recursive_then_values_then_keys(self):
        r = _resolve_path(_XHR, _parse_path("...endpoints[values][keys]"))
        assert "get" in r
        assert "post" in r

    def test_recursive_glob_then_key(self):
        # *price* matches the key "class" with value "price" — not a key named *price*
        # The span dicts have class="price", so ...*price* finds nothing (class value, not key name)
        # Use ...span.text instead to get price text
        r = _resolve_path(_SHOP, _parse_path("...span.text"))
        assert "$49.99" in r
        assert "$99.50" in r

    # ── [=filter] chaining ───────────────────────────────────────────────

    def test_value_filter_then_nothing(self):
        r = _resolve_path(_SHOP, _parse_path("...text[=*$*]"))
        assert "$49.99" in r
        assert "$99.50" in r
        assert "$249.00" in r
        assert "Home" not in r

    def test_value_filter_regex(self):
        r = _resolve_path(_SHOP, _parse_path("...text[=/^\\$\\d+\\.\\d{2}$/]"))
        assert "$49.99" in r
        assert "$99.50" in r

    def test_value_filter_negation(self):
        r = _resolve_path(_SHOP, _parse_path("...h2[!=Widget]"))
        assert "Widget" not in r
        assert "Gadget" in r
        assert "Deluxe" in r

    # ── [key=filter] chaining ────────────────────────────────────────────

    def test_key_filter_then_key(self):
        r = _resolve_path(_SHOP, _parse_path("...section[class=product].h2"))
        assert r == ["Widget", "Gadget"]

    def test_key_filter_negation_then_key(self):
        r = _resolve_path(_SHOP, _parse_path("...section[class!=product].h2"))
        assert r == ["Deluxe"]

    def test_key_filter_glob(self):
        r = _resolve_path(_SHOP, _parse_path("...section[class=*pro*].h2"))
        assert "Widget" in r
        assert "Gadget" in r

    def test_glob_key_filter(self):
        r = _resolve_path(_SHOP, _parse_path("...*[*=sidebar]"))
        assert len(r) >= 1
        assert r[0].get("class") == "sidebar"

    def test_key_filter_regex(self):
        r = _resolve_path(_SHOP, _parse_path("...section[class=/^prod/].h2"))
        assert r == ["Widget", "Gadget"]

    # ── ~N context expansion chaining ────────────────────────────────────

    def test_tilde_after_filter(self):
        r = _resolve_path(_SHOP, _parse_path("...text[=*$49*]~1"))
        assert len(r) == 1
        assert r[0].get("class") == "price"

    def test_tilde_after_filter_then_key(self):
        r = _resolve_path(_SHOP, _parse_path("...text[=*$49*]~1.class"))
        assert r == ["price"]

    def test_tilde_then_keys(self):
        r = _resolve_path(_SHOP, _parse_path("...text[=*$49*]~2[keys]"))
        assert "h2" in r
        assert "span" in r

    def test_tilde_then_sibling(self):
        """CSS h3 + p equivalent: find value, go up, navigate to sibling."""
        r = _resolve_path(_SHOP, _parse_path("...text[=*$49*]~2.h2"))
        assert r == ["Widget"]

    def test_tilde_then_recursive(self):
        r = _resolve_path(_SHOP, _parse_path("...text[=*$49*]~2...text"))
        assert "$49.99" in r
        assert "sale" in r

    def test_deep_tilde(self):
        r = _resolve_path(_SHOP, _parse_path("...text[=*$49*]~3[keys]"))
        # ~3 from "$49.99" text goes up: span→section→main dict
        assert "id" in r or "class" in r or "section" in r

    # ── JSON string auto-parse chaining ──────────────────────────────────

    def test_json_autoparse_then_keys(self):
        r = _resolve_path(_XHR, _parse_path("xhr.body.endpoints[keys]"))
        assert "/products" in r

    def test_json_autoparse_deep_chain(self):
        r = _resolve_path(_XHR, _parse_path("xhr.body.endpoints[values][values]...summary"))
        assert "List products" in r
        assert "Create product" in r
        assert "Remove user" in r

    def test_json_autoparse_then_filter(self):
        r = _resolve_path(_XHR, _parse_path("xhr.body.endpoints[keys][=*/products*]"))
        assert r == ["/products"]

    # ── OR / AND with complex paths ──────────────────────────────────────

    def test_or_with_filters(self):
        r = resolve_expression(_SHOP, "...h2[=Widget] | ...h2[=Deluxe]")
        assert "Widget" in r
        assert "Deluxe" in r
        assert "Gadget" not in r

    def test_and_both_present(self):
        r = resolve_expression(_SHOP, "...h2 & ...span.text")
        assert "Widget" in r
        assert "$49.99" in r

    def test_and_one_missing(self):
        r = resolve_expression(_SHOP, "...h2 & ...nonexistent")
        assert r is None

    def test_or_with_tilde(self):
        r = resolve_expression(_SHOP, "...text[=*$49*]~2.h2 | ...text[=*$249*]~2.h2")
        assert "Widget" in r
        assert "Deluxe" in r

    # ── Escaped keys ─────────────────────────────────────────────────────

    def test_escaped_key_with_dots(self):
        obj = {"a.b": {"c": 42}}
        assert _resolve_path(obj, _parse_path("(a.b).c")) == 42

    def test_recursive_escaped_key(self):
        obj = {"nested": {"a.b": 99}}
        r = _resolve_path(obj, _parse_path("...(a.b)"))
        assert r == [99]

    # ── Per-item mapping edge cases ──────────────────────────────────────

    def test_map_then_filter(self):
        r = _resolve_path(_SHOP, _parse_path("...section.h2[!=Gadget]"))
        assert "Widget" in r
        assert "Deluxe" in r
        assert "Gadget" not in r

    def test_map_nested_lists(self):
        r = _resolve_path(_SHOP, _parse_path("...li.text"))
        assert "sale" in r
        assert "popular" in r
        assert "new" in r
        assert "premium" in r

    def test_map_then_slice(self):
        r = _resolve_path(_SHOP, _parse_path("...section[0:2].span.text"))
        assert r == ["$49.99", "$99.50"]

    # ── Matcher edge cases ───────────────────────────────────────────────

    def test_matcher_skips_dicts(self):
        m = _build_matcher("test")
        assert m({"test": 1}) is False  # dict should not match

    def test_matcher_skips_lists(self):
        m = _build_matcher("test")
        assert m(["test"]) is False  # list should not match

    def test_matcher_matches_numbers(self):
        m = _build_matcher("42")
        assert m(42) is True
        assert m(43) is False

    def test_matcher_skips_none(self):
        m = _build_matcher("test")
        assert m(None) is False

    # ── HTML-like structure with [id=] ───────────────────────────────────

    def test_find_by_id(self):
        r = _resolve_path(_SHOP, _parse_path("...*[id=products]"))
        assert len(r) >= 1
        assert "section" in r[0]

    def test_find_by_id_then_drill(self):
        r = _resolve_path(_SHOP, _parse_path("...*[id=products]...h2"))
        assert "Widget" in r
        assert "Gadget" in r
        assert "Deluxe" in r

    # ── mailto extraction pattern ────────────────────────────────────────

    def test_mailto_extraction(self):
        r = _resolve_path(_SHOP, _parse_path("...a[href=*mailto*].text"))
        assert r == ["shop@example.com"]

    def test_mailto_href(self):
        r = _resolve_path(_SHOP, _parse_path("...a[href=*mailto*].href"))
        assert r == ["mailto:shop@example.com"]
