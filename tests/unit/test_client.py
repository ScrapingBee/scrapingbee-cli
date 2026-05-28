"""Unit tests for client module (parse_usage, pretty_json, retry logic)."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from scrapingbee_cli.client import Client, _clean_params, parse_usage, pretty_json


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


def _call_with(method_name: str, tag):
    """Invoke a Client method by name with a minimal positional arg, optionally passing tag.

    Returns the (path, cleaned_params) recorded by the patched _get. Methods all
    funnel through Client._get (directly or via _get_with_retry), so patching
    _get captures the params dict and _clean_params() mirrors what hits the wire.
    """

    async def run():
        client = Client("fake-key")
        captured: dict = {}

        async def fake_get(path, params, headers=None):
            captured["path"] = path
            captured["params"] = _clean_params(params)
            return (b"{}", {}, 200)

        with patch.object(client, "_get", new=AsyncMock(side_effect=fake_get)):
            method = getattr(client, method_name)
            kwargs = {"tag": tag} if tag is not None else {}
            # Disable retries so failures don't loop on the stub.
            kwargs["retries"] = 0
            await method(_FIRST_ARG[method_name], **kwargs)
        return captured

    return asyncio.run(run())


_FIRST_ARG = {
    "scrape": "https://example.com",
    "google_search": "coffee",
    "fast_search": "coffee",
    "amazon_product": "B000000000",
    "amazon_pricing": "B000000000",
    "amazon_search": "coffee",
    "walmart_search": "coffee",
    "walmart_product": "12345",
    "youtube_search": "coffee",
    "youtube_metadata": "dQw4w9WgXcQ",
    "chatgpt": "hello",
}


class TestTagParam:
    """Tests that --tag is forwarded as ?tag=... when set, and omitted when not."""

    @pytest.mark.parametrize("method_name", list(_FIRST_ARG))
    def test_tag_sent_when_set(self, method_name):
        captured = _call_with(method_name, tag="my-tag")
        assert captured["params"].get("tag") == "my-tag"

    @pytest.mark.parametrize("method_name", list(_FIRST_ARG))
    def test_tag_omitted_when_unset(self, method_name):
        captured = _call_with(method_name, tag=None)
        assert "tag" not in captured["params"]


class TestGoogleDateRange:
    """Tests that google_search forwards date_range only when set."""

    @pytest.mark.parametrize(
        "value", ["past_hour", "past_day", "past_week", "past_month", "past_year"]
    )
    def test_date_range_sent_when_set(self, value):
        async def run():
            client = Client("fake-key")
            captured: dict = {}

            async def fake_get(path, params, headers=None):
                captured["params"] = _clean_params(params)
                return (b"{}", {}, 200)

            with patch.object(client, "_get", new=AsyncMock(side_effect=fake_get)):
                await client.google_search("coffee", date_range=value, retries=0)
            assert captured["params"].get("date_range") == value

        asyncio.run(run())

    def test_date_range_omitted_when_unset(self):
        async def run():
            client = Client("fake-key")
            captured: dict = {}

            async def fake_get(path, params, headers=None):
                captured["params"] = _clean_params(params)
                return (b"{}", {}, 200)

            with patch.object(client, "_get", new=AsyncMock(side_effect=fake_get)):
                await client.google_search("coffee", retries=0)
            assert "date_range" not in captured["params"]

        asyncio.run(run())
