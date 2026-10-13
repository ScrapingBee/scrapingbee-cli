"""Regression tests: the API key must not come back out of an error body.

The API answers a wrong key with 401 ``{"message": "Invalid api key: <key>"}``.
Every command prints error bodies to stderr (and batch writes them to .err
files), so the full key ended up in terminals, logs and agent transcripts.

These tests run the real Client against a local fake API endpoint.
"""

from __future__ import annotations

import asyncio

from aiohttp import web

from scrapingbee_cli.client import Client

KEY = "FAKEKEY1234567890abcdef"


def _call_fake_api(status, call, key=KEY):
    """Run ``call(client)`` against an endpoint that echoes the key with ``status``."""

    async def endpoint(request):
        return web.json_response({"message": f"Invalid api key: {KEY}"}, status=status)

    async def run():
        app = web.Application()
        app.router.add_route("*", "/{tail:.*}", endpoint)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = runner.addresses[0][1]
        try:
            async with Client(key, base_url=f"http://127.0.0.1:{port}") as client:
                return await call(client)
        finally:
            await runner.cleanup()

    return asyncio.run(run())


class TestKeyIsRedactedInErrorBodies:
    def test_get_401_body_does_not_contain_the_key(self):
        data, _, status = _call_fake_api(401, lambda c: c.usage(retries=0))
        assert status == 401
        assert KEY.encode() not in data
        assert b"Invalid api key: [redacted]" in data

    def test_post_401_body_does_not_contain_the_key(self):
        data, _, status = _call_fake_api(
            401, lambda c: c.scrape("https://example.com", method="post", body="x=1", retries=0)
        )
        assert status == 401
        assert KEY.encode() not in data

    def test_key_with_trailing_whitespace_is_still_redacted(self):
        data, _, _ = _call_fake_api(401, lambda c: c.usage(retries=0), key=KEY + " ")
        assert KEY.encode() not in data

    def test_success_body_is_left_alone(self):
        data, _, status = _call_fake_api(200, lambda c: c.usage(retries=0))
        assert status == 200
        assert KEY.encode() in data
