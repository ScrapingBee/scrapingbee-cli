"""Regression tests: user -H headers must never clobber the API's Bearer auth.

With header-based auth (SCR-585), the session carries ``Authorization: Bearer
<api key>``. aiohttp lets per-request headers override session headers on the
same (case-insensitive) key, so passing a user's ``-H "Authorization: …"``
through raw on POST/PUT replaced our key and the API rejected the request
(400/401). Custom headers are therefore always ``Spb-``-prefixed — which is
also the only form the API forwards to the target (raw custom headers were
silently dropped on POST/PUT).

These tests run the real Client against a local fake API endpoint and assert
on the headers that actually arrive on the wire.
"""

from __future__ import annotations

import asyncio

from aiohttp import web

from scrapingbee_cli.client import Client


def _run_against_fake_api(method, custom_headers):
    """Return the (headers, query) the fake ScrapingBee endpoint received."""
    seen = {}

    async def endpoint(request):
        seen["headers"] = dict(request.headers)
        seen["query"] = dict(request.query)
        return web.json_response({"ok": True})

    async def run():
        app = web.Application()
        app.router.add_route("*", "/", endpoint)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = runner.addresses[0][1]
        try:
            async with Client("fake-key", base_url=f"http://127.0.0.1:{port}") as client:
                await client.scrape(
                    "https://example.com",
                    method=method,
                    body="x=1" if method != "get" else None,
                    custom_headers=custom_headers,
                    forward_headers_pure=True,
                    retries=0,
                )
        finally:
            await runner.cleanup()

    asyncio.run(run())
    return seen["headers"], seen["query"]


class TestUserAuthorizationHeaderDoesNotClobberApiAuth:
    def test_post_with_user_basic_auth_header_still_authenticates(self):
        headers, _ = _run_against_fake_api("post", {"Authorization": "Basic Zm9vOmJhcg=="})
        assert headers.get("Authorization") == "Bearer fake-key"
        assert headers.get("Spb-Authorization") == "Basic Zm9vOmJhcg=="

    def test_put_with_user_token_header_still_authenticates(self):
        headers, _ = _run_against_fake_api("put", {"Authorization": "Token abc"})
        assert headers.get("Authorization") == "Bearer fake-key"
        assert headers.get("Spb-Authorization") == "Token abc"

    def test_get_with_user_auth_header_is_prefixed_and_keeps_bearer(self):
        headers, _ = _run_against_fake_api("get", {"Authorization": "Basic Zm9vOmJhcg=="})
        assert headers.get("Authorization") == "Bearer fake-key"
        assert headers.get("Spb-Authorization") == "Basic Zm9vOmJhcg=="


class TestSpbPrefixing:
    def test_already_prefixed_header_is_not_double_prefixed(self):
        headers, _ = _run_against_fake_api("post", {"Spb-X-Custom": "1"})
        assert headers.get("Spb-X-Custom") == "1"
        assert "Spb-Spb-X-Custom" not in headers

    def test_user_content_type_goes_to_target_api_content_type_intact(self):
        # The user's Content-Type must travel as Spb-Content-Type (for the
        # target), while the request to the API itself stays form-encoded.
        headers, _ = _run_against_fake_api("post", {"Content-Type": "application/json"})
        assert headers.get("Spb-Content-Type") == "application/json"
        assert headers.get("Content-Type", "").startswith("application/x-www-form-urlencoded")
