"""Unit tests for client module (parse_usage, pretty_json)."""

from __future__ import annotations

import json

from scrapingbee_cli.client import parse_usage, pretty_json


class TestParseUsage:
    """Tests for parse_usage()."""

    def test_empty_body_returns_defaults(self):
        out = parse_usage(b"")
        assert out["max_concurrency"] == 5
        assert out["credits"] == 0

    def test_invalid_json_returns_defaults(self):
        out = parse_usage(b"not json")
        assert out["max_concurrency"] == 5
        assert out["credits"] == 0

    def test_max_concurrency_from_various_keys(self):
        for key in (
            "max_concurrency",
            "max_concurrent_requests",
            "concurrent_request_limit",
            "concurrency",
            "concurrent_requests",
        ):
            body = json.dumps({key: 10}).encode()
            out = parse_usage(body)
            assert out["max_concurrency"] == 10

    def test_credits_from_various_keys(self):
        body = json.dumps({"credits": 100}).encode()
        out = parse_usage(body)
        assert out["credits"] == 100

        body = json.dumps({"available_credits": 50}).encode()
        out = parse_usage(body)
        assert out["credits"] == 50

    def test_credits_from_max_minus_used(self):
        body = json.dumps({"max_api_credit": 100, "used_api_credit": 30}).encode()
        out = parse_usage(body)
        assert out["credits"] == 70

    def test_full_usage_response(self):
        body = json.dumps(
            {
                "max_concurrency": 3,
                "credits": 42,
            }
        ).encode()
        out = parse_usage(body)
        assert out["max_concurrency"] == 3
        assert out["credits"] == 42


class TestPrettyJson:
    """Tests for pretty_json()."""

    def test_valid_json_pretty_prints(self):
        data = b'{"a":1,"b":2}'
        out = pretty_json(data)
        parsed = json.loads(out)
        assert parsed == {"a": 1, "b": 2}
        assert "  " in out  # indentation

    def test_invalid_json_returns_decoded_string(self):
        data = b"<html>not json</html>"
        out = pretty_json(data)
        assert "<html>" in out
