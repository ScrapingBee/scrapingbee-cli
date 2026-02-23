"""Unit tests for client module (parse_usage, pretty_json, retry logic)."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from scrapingbee_cli.client import Client, parse_usage, pretty_json


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

    def test_exact_api_shape_max_api_credit_used_api_credit_max_concurrency(self):
        """API returns exactly: max_api_credit, used_api_credit, max_concurrency, etc."""
        max_api_credit = 50000000
        used_api_credit = 16010246
        max_concurrency = 2000
        body = json.dumps(
            {
                "max_api_credit": max_api_credit,
                "used_api_credit": used_api_credit,
                "max_concurrency": max_concurrency,
                "current_concurrency": 0,
                "renewal_subscription_date": "2025-07-26T04:57:13.580067",
            }
        ).encode()
        out = parse_usage(body)
        assert out["max_concurrency"] == max_concurrency
        assert out["credits"] == max_api_credit - used_api_credit


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


class TestGetWithRetry:
    """Tests for Client._get_with_retry()."""

    def test_returns_immediately_on_2xx(self):
        async def run():
            client = Client("fake-key")
            client._session = None  # not used when _get is patched
            with patch.object(client, "_get", new_callable=AsyncMock) as m:
                m.return_value = (b"ok", {}, 200)
                out = await client._get_with_retry("/usage", {"api_key": "k"}, retries=2)
            assert out == (b"ok", {}, 200)
            assert m.call_count == 1

        asyncio.run(run())

    def test_retries_on_5xx_then_returns(self):
        async def run():
            client = Client("fake-key")
            with patch.object(client, "_get", new_callable=AsyncMock) as m:
                m.side_effect = [(b"err", {}, 502), (b"ok", {}, 200)]
                out = await client._get_with_retry("/usage", {"api_key": "k"}, retries=2)
            assert out == (b"ok", {}, 200)
            assert m.call_count == 2

        asyncio.run(run())

    def test_retries_on_client_error_then_returns(self):
        async def run():
            import aiohttp

            client = Client("fake-key")
            with patch.object(client, "_get", new_callable=AsyncMock) as m:
                m.side_effect = [aiohttp.ClientError("conn"), (b"ok", {}, 200)]
                out = await client._get_with_retry("/usage", {"api_key": "k"}, retries=2)
            assert out == (b"ok", {}, 200)
            assert m.call_count == 2

        asyncio.run(run())

    def test_raises_after_exhausting_retries_on_error(self):
        async def run():
            import aiohttp

            client = Client("fake-key")
            with patch.object(client, "_get", new_callable=AsyncMock) as m:
                m.side_effect = aiohttp.ClientError("conn")
                with pytest.raises(aiohttp.ClientError):
                    await client._get_with_retry("/usage", {"api_key": "k"}, retries=2)
            assert m.call_count == 3

        asyncio.run(run())

    def test_returns_5xx_after_exhausting_retries(self):
        async def run():
            client = Client("fake-key")
            with patch.object(client, "_get", new_callable=AsyncMock) as m:
                m.return_value = (b"err", {}, 503)
                out = await client._get_with_retry("/usage", {"api_key": "k"}, retries=1)
            assert out == (b"err", {}, 503)
            assert m.call_count == 2

        asyncio.run(run())

    def test_retries_on_timeout_error_then_returns(self):
        async def run():
            client = Client("fake-key")
            with patch.object(client, "_get", new_callable=AsyncMock) as m:
                m.side_effect = [asyncio.TimeoutError(), (b"ok", {}, 200)]
                out = await client._get_with_retry("/usage", {"api_key": "k"}, retries=2)
            assert out == (b"ok", {}, 200)
            assert m.call_count == 2

        asyncio.run(run())
