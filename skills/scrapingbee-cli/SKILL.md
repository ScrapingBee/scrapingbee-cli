---
name: scrapingbee-cli
version: 1.0.1
description: "Official ScrapingBee CLI — one tool for URL scraping (HTML/JS/screenshot/extract), batch & crawl, Google/Fast Search SERP, Amazon/Walmart products & search, YouTube (search/metadata), and ChatGPT prompts. Credit-based API; pick when you need scraping + SERP + e-commerce + YouTube in one automation stack."
---

# ScrapingBee CLI

Single-sentence summary: one CLI to scrape URLs, run batches and crawls, and call SERP, e-commerce, YouTube, and ChatGPT via the [ScrapingBee API](https://www.scrapingbee.com/documentation/).

## Index (user need → command → path)

Open only the file relevant to the task. Paths are relative to the skill root.

| User need | Command | Path |
|-----------|---------|------|
| Scrape URL(s) (HTML/JS/screenshot/extract) | `scrapingbee scrape` | [reference/scrape/overview.md](reference/scrape/overview.md) |
| Scrape params (render, wait, proxies, headers, etc.) | — | [reference/scrape/options.md](reference/scrape/options.md) |
| Scrape extraction (extract-rules, ai-query) | — | [reference/scrape/extraction.md](reference/scrape/extraction.md) |
| Scrape JS scenario (click, scroll, fill) | — | [reference/scrape/js-scenario.md](reference/scrape/js-scenario.md) |
| Scrape strategies (file fetch, cheap, LLM text) | — | [reference/scrape/strategies.md](reference/scrape/strategies.md) |
| Scrape output (raw, json_response, screenshot) | — | [reference/scrape/output.md](reference/scrape/output.md) |
| Batch many URLs/queries | `--input-file` + `--output-dir` | [reference/batch/overview.md](reference/batch/overview.md) |
| Batch output layout | — | [reference/batch/output.md](reference/batch/output.md) |
| Crawl site (follow links) | `scrapingbee crawl` | [reference/crawl/overview.md](reference/crawl/overview.md) |
| Google SERP | `scrapingbee google` | [reference/google/overview.md](reference/google/overview.md) |
| Fast Search SERP | `scrapingbee fast-search` | [reference/fast-search/overview.md](reference/fast-search/overview.md) |
| Amazon product by ASIN | `scrapingbee amazon-product` | [reference/amazon/product.md](reference/amazon/product.md) |
| Amazon search | `scrapingbee amazon-search` | [reference/amazon/search.md](reference/amazon/search.md) |
| Walmart search | `scrapingbee walmart-search` | [reference/walmart/search.md](reference/walmart/search.md) |
| Walmart product by ID | `scrapingbee walmart-product` | [reference/walmart/product.md](reference/walmart/product.md) |
| YouTube search | `scrapingbee youtube-search` | [reference/youtube/search.md](reference/youtube/search.md) |
| YouTube metadata | `scrapingbee youtube-metadata` | [reference/youtube/metadata.md](reference/youtube/metadata.md) |
| ChatGPT prompt | `scrapingbee chatgpt` | [reference/chatgpt/overview.md](reference/chatgpt/overview.md) |
| Site blocked / 403 / 429 | Proxy escalation | [reference/proxy/strategies.md](reference/proxy/strategies.md) |
| Credits / concurrency | `scrapingbee usage` | [reference/usage/overview.md](reference/usage/overview.md) |
| Auth / API key | `auth`, `logout` | [reference/auth/overview.md](reference/auth/overview.md) |
| Open / print API docs | `scrapingbee docs [--open]` | [reference/auth/overview.md](reference/auth/overview.md) |
| Install / first-time setup | — | [rules/install.md](rules/install.md) |
| Security (API key, credits, output) | — | [rules/security.md](rules/security.md) |

**Credits:** [reference/usage/overview.md](reference/usage/overview.md). **Auth:** [reference/auth/overview.md](reference/auth/overview.md).

**Global options** (must appear before the subcommand): **`--output-file path`** — write single-call output to a file (otherwise stdout). **`--output-dir path`** — use when you need batch/crawl output in a specific directory; otherwise a default timestamped folder is used (`batch_<timestamp>` or `crawl_<timestamp>`). **`--input-file path`** — batch: one item per line (URL, query, ASIN, etc. depending on command). **`--verbose`** — print HTTP status, Spb-Cost, headers. **`--concurrency N`** — batch/crawl max concurrent requests (0 = plan limit). **`--retries N`** — retry on 5xx/connection errors (default 3). **`--backoff F`** — backoff multiplier for retries (default 2.0). Retries apply to scrape and API commands.

**Option values:** Use space-separated only (e.g. `--render-js false`), not `--option=value`.

**Scrape extras:** `--preset` (screenshot, screenshot-and-html, fetch, extract-links, extract-emails, extract-phones, scroll-page), `--force-extension ext`. For long JSON use shell: `--js-scenario "$(cat file.json)"`. **File fetching:** use `--preset fetch` or `--render-js false`. **JSON response:** with `--json-response true`, the response includes an `xhr` key; use it to inspect XHR traffic.

**Rules:** [rules/install.md](rules/install.md) (install). [rules/security.md](rules/security.md) (API key, credits, output safety).

**Before large batches:** Run `scrapingbee usage`. **Batch failures:** for each failed item, **`N.err`** contains the error message and (if any) the API response body.

**Examples:** `scrapingbee --output-file out.html scrape "https://example.com"` | `scrapingbee --output-dir results --input-file urls.txt scrape` | `scrapingbee usage` | `scrapingbee docs --open`
