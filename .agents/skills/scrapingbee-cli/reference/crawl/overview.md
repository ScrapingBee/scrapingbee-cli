# Crawl

> **Requires Scrapy extra:** `pip install "scrapingbee-cli[crawl]"`. Without it, the `crawl` command prints an install hint and exits. All other commands work without it.

Three modes: **Scrapy project** (named spider), **URL-based** (start URL(s), follow links), or **sitemap** (`--from-sitemap`). URL-based uses same options as scrape; see [reference/scrape/overview.md](reference/scrape/overview.md) for params (render-js, return-page-markdown, premium-proxy, etc.).

## Scrapy project

Requires directory with **`scrapy.cfg`** (or **`--project` / `-p`** path). Spider must use scrapy-scrapingbee.

```bash
scrapingbee crawl myspider
scrapingbee crawl myspider --project /path/to/project
```

Concurrency: **`--concurrency`** or usage API limit.

## URL-based

```bash
scrapingbee crawl "https://example.com"
scrapingbee crawl "https://example.com" --max-depth 3 --max-pages 100 --render-js false
scrapingbee crawl --output-dir my-crawl "https://example.com"
```

## Sitemap crawl

Fetch all page URLs from a sitemap.xml (handles sitemap indexes automatically) and crawl them:

```bash
scrapingbee crawl --output-dir crawl-out --from-sitemap "https://example.com/sitemap.xml"
scrapingbee crawl --output-dir crawl-out --from-sitemap "https://example.com/sitemap.xml" --return-page-markdown true
```

Crawl does **not** use the global `--output-file` option. It writes one file per page (numbered `1.<ext>`, `2.<ext>`, …) under `--output-dir`; extension comes from scrape params or URL/Content-Type. A `manifest.json` is also written mapping each URL to its filename.

## Resume an interrupted crawl

```bash
scrapingbee crawl --output-dir my-crawl --resume "https://example.com"
```

With `--resume`, already-crawled URLs (from `manifest.json` in the output dir) are skipped. Use `--output-dir` pointing to the previous run folder.

| Parameter | Description |
|-----------|-------------|
| `--max-depth` | Max link depth (0 = unlimited). Default 0. |
| `--max-pages` | Max pages to fetch (0 = unlimited). Default 0. |
| `--output-dir` | Use when you need output in a specific directory; otherwise default is `crawl_<timestamp>`. |
| `--from-sitemap` | URL of a sitemap.xml to fetch URLs from (handles sitemap indexes). |
| `--allowed-domains` | Comma-separated domains. Default: same as start URL(s). |
| `--allow-external-domains` | Follow any domain. Default: same domain only. |
| `--download-delay` | Seconds between requests (Scrapy DOWNLOAD_DELAY). |
| `--autothrottle` | Enable Scrapy AutoThrottle to adapt request rate. |

Scrape options (render-js, return-page-markdown, screenshot, premium-proxy, wait, headers, cookies) apply per request. Concurrency: **`--concurrency`** or usage API; same cap as batch.

**Output:** One file per page; extension from scrape params or URL/Content-Type.

**Crawl with AI extraction or non-HTML output:** Options that return JSON, images, or plain text without extractable links — `--ai-query`, `--ai-extract-rules`, `--extract-rules`, `--screenshot` (without `--json-response true`), `--return-page-text` — have no HTML links for the crawler to follow. The crawler **automatically does discovery**: it saves your response, then fetches the same URL as plain HTML to find links, so crawling continues normally. Each affected page costs 2 requests. `--return-page-markdown` is the exception: markdown links (e.g. `[text](url)`) are extracted directly from the response, so no second request is needed. No extra steps required for any of these. For the common “crawl then summarize/extract” workflow, see [reference/usage/patterns.md](reference/usage/patterns.md).
