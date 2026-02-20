"""Helpers for integration tests: API matrix builder."""

from __future__ import annotations


def build_api_matrix_tests(
    base: list[str],
    api_timeout: int = 90,
    chatgpt_timeout: int = 150,
) -> list[tuple[str, list[str], int]]:
    """Build one test per (command, parameter). Excludes --input-file."""
    tests: list[tuple[str, list[str], int]] = []

    tests.append(("usage", base + ["usage"], api_timeout))

    scrape_base = base + ["scrape", "https://httpbin.scrapingbee.com/"]
    for opt, val in [
        ("--render-js", "false"),
        ("--js-scenario", '{"instructions": [{"wait": 100}]}'),
        ("--wait", "1000"),
        ("--wait-for", "body"),
        ("--wait-browser", "load"),
        ("--block-ads", "false"),
        ("--block-resources", "false"),
        ("--window-width", "1920"),
        ("--window-height", "1080"),
        ("--premium-proxy", "false"),
        ("--stealth-proxy", "false"),
        ("--country-code", "us"),
        ("--own-proxy", ""),
        ("--forward-headers", "false"),
        ("--forward-headers-pure", "false"),
        ("--json-response", "false"),
        ("--screenshot", "false"),
        ("--screenshot-selector", "body"),
        ("--screenshot-full-page", "false"),
        ("--return-page-source", "false"),
        ("--return-markdown", "false"),
        ("--return-text", "false"),
        ("--extract-rules", ""),
        ("--ai-query", "type of content in the page"),
        ("--ai-selector", "body"),
        ("--ai-extract-rules", '{"body":"content in markdown"}'),
        ("--session-id", "1"),
        ("--timeout", "10000"),
        ("--cookies", "session=abc123,domain=example.com;name=value"),
        ("--device", "desktop"),
        ("--custom-google", "false"),
        ("--transparent-status-code", "false"),
        ("--scraping-config", ""),
        ("-X", "GET"),
    ]:
        tests.append((f"scrape {opt}", scrape_base + [opt, val], api_timeout))
    tests.append(
        (
            "scrape -H header",
            scrape_base + ["-H", "Accept-Language:en", "--forward-headers", "true"],
            api_timeout,
        )
    )
    tests.append(
        (
            "scrape POST body",
            base
            + [
                "scrape",
                "https://httpbin.scrapingbee.com/post",
                "-X",
                "POST",
                "-d",
                "{}",
                "--content-type",
                "application/json",
            ],
            api_timeout,
        )
    )

    for opt, val in [
        ("", ""),
        ("--search-type", "classic"),
        ("--country-code", "us"),
        ("--device", "desktop"),
        ("--page", "1"),
        ("--language", "en"),
        ("--nfpr", "false"),
        ("--extra-params", ""),
        ("--add-html", "false"),
        ("--light-request", "false"),
    ]:
        name = f"google {opt}" if opt else "google"
        cmd = base + ["google", "test query"] + ([opt, val] if opt else [])
        tests.append((name, cmd, api_timeout))

    for opt, val in [
        ("", ""),
        ("--page", "1"),
        ("--country-code", "us"),
        ("--language", "en"),
    ]:
        name = f"fast-search {opt}" if opt else "fast-search"
        cmd = base + ["fast-search", "ai news"] + ([opt, val] if opt else [])
        tests.append((name, cmd, api_timeout))

    for opt, val in [
        ("", ""),
        ("--device", "desktop"),
        ("--domain", "com"),
        ("--country", "us"),
        ("--zip-code", "10001"),
        ("--language", "en_US"),
        ("--currency", "USD"),
        ("--add-html", "false"),
        ("--light-request", "false"),
        ("--screenshot", "false"),
    ]:
        name = f"amazon-product {opt}" if opt else "amazon-product"
        cmd = base + ["amazon-product", "B0947BJ67M"] + ([opt, val] if opt else [])
        tests.append((name, cmd, api_timeout))

    for opt, val in [
        ("", ""),
        ("--start-page", "1"),
        ("--pages", "1"),
        ("--sort-by", "bestsellers"),
        ("--device", "desktop"),
        ("--domain", "com"),
        ("--country", "us"),
        ("--zip-code", "10001"),
        ("--language", "en_US"),
        ("--currency", "USD"),
        ("--category-id", "1"),
        ("--merchant-id", "all"),
        ("--autoselect-variant", "false"),
        ("--add-html", "false"),
        ("--light-request", "false"),
        ("--screenshot", "false"),
    ]:
        name = f"amazon-search {opt}" if opt else "amazon-search"
        cmd = base + ["amazon-search", "laptop"] + ([opt, val] if opt else [])
        tests.append((name, cmd, api_timeout))

    for opt, val in [
        ("", ""),
        ("--min-price", "10"),
        ("--max-price", "100"),
        ("--sort-by", "best_match"),
        ("--device", "desktop"),
        ("--domain", "com"),
        ("--fulfillment-speed", "today"),
        ("--fulfillment-type", "in_store"),
        ("--delivery-zip", "10001"),
        ("--store-id", "1"),
        ("--add-html", "false"),
        ("--light-request", "false"),
        ("--screenshot", "false"),
    ]:
        name = f"walmart-search {opt}" if opt else "walmart-search"
        cmd = base + ["walmart-search", "headphones"] + ([opt, val] if opt else [])
        tests.append((name, cmd, api_timeout))

    for opt, val in [
        ("", ""),
        ("--domain", "com"),
        ("--delivery-zip", "10001"),
        ("--store-id", "1"),
        ("--add-html", "false"),
        ("--light-request", "false"),
        ("--screenshot", "false"),
    ]:
        name = f"walmart-product {opt}" if opt else "walmart-product"
        cmd = base + ["walmart-product", "5326288984"] + ([opt, val] if opt else [])
        tests.append((name, cmd, api_timeout))

    for opt, val in [
        ("", ""),
        ("--upload-date", "this_week"),
        ("--type", "video"),
        ("--duration", "4-20"),
        ("--sort-by", "relevance"),
        ("--hd", "false"),
        ("--4k", "false"),
        ("--subtitles", "false"),
        ("--creative-commons", "false"),
        ("--live", "false"),
        ("--360", "false"),
        ("--3d", "false"),
        ("--hdr", "false"),
        ("--location", "false"),
        ("--vr180", "false"),
    ]:
        name = f"youtube-search {opt}" if opt else "youtube-search"
        cmd = base + ["youtube-search", "python tutorial"] + ([opt, val] if opt else [])
        tests.append((name, cmd, api_timeout))

    tests.append(("youtube-metadata", base + ["youtube-metadata", "dQw4w9WgXcQ"], api_timeout))

    for opt, val in [
        ("", ""),
        ("--language", "en"),
        ("--transcript-origin", "auto_generated"),
    ]:
        name = f"youtube-transcript {opt}" if opt else "youtube-transcript"
        cmd = base + ["youtube-transcript", "dQw4w9WgXcQ"] + ([opt, val] if opt else [])
        tests.append((name, cmd, api_timeout))

    tests.append(
        (
            "youtube-trainability",
            base + ["youtube-trainability", "dQw4w9WgXcQ"],
            api_timeout,
        )
    )
    tests.append(("chatgpt", base + ["chatgpt", "Say hello"], chatgpt_timeout))

    return tests


# Commands for help / no-api-key parametrized tests
CLI_COMMANDS = [
    ("usage", []),
    ("scrape", ["https://httpbin.scrapingbee.com/"]),
    ("google", ["query"]),
    ("fast-search", ["query"]),
    ("amazon-product", ["B001"]),
    ("amazon-search", ["query"]),
    ("walmart-search", ["query"]),
    ("walmart-product", ["1"]),
    ("youtube-search", ["query"]),
    ("youtube-metadata", ["dQw4w9WgXcQ"]),
    ("youtube-transcript", ["dQw4w9WgXcQ"]),
    ("youtube-trainability", ["dQw4w9WgXcQ"]),
    ("chatgpt", ["hi"]),
]
