# Crawl

Two modes: **Scrapy project** (named spider) or **URL-based** (start URL(s), follow links). URL-based uses same options as scrape; see [reference/scrape/overview.md](reference/scrape/overview.md) for params (render-js, return-page-markdown, premium-proxy, etc.).

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
scrapingbee crawl "https://example.com" --output-dir .scrapingbee/crawl
```

Crawl does **not** use the global `--output-file` option. It writes one file per page (numbered `1.<ext>`, `2.<ext>`, …) under `--output-dir`; extension comes from scrape params or URL/Content-Type.

| Parameter | Description |
|-----------|-------------|
| `--max-depth` | Max link depth (0 = unlimited). Default 0. |
| `--max-pages` | Max pages to fetch (0 = unlimited). Default 0. |
| `--output-dir` | Use when you need output in a specific directory; otherwise default is `crawl_<timestamp>`. |
| `--allowed-domains` | Comma-separated domains. Default: same as start URL(s). |
| `--allow-external-domains` | Follow any domain. Default: same domain only. |
| `--download-delay` | Seconds between requests (Scrapy DOWNLOAD_DELAY). |
| `--autothrottle` | Enable Scrapy AutoThrottle to adapt request rate. |

Scrape options (render-js, return-page-markdown, screenshot, premium-proxy, wait, headers, cookies) apply per request. Concurrency: **`--concurrency`** or usage API; same cap as batch.

**Output:** One file per page; extension from scrape params or URL/Content-Type. Screenshot without json_response: no link discovery from that response.
