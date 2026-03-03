# Scrape (HTML API)

Fetch one URL or many (batch). Use for HTML, JS-rendered pages, screenshots, or extracted data. **For large responses**, use **`--output-file path`** or (batch) **`--output-dir`** (before or after command) so output goes to files instead of stdout.

## Command

```bash
scrapingbee scrape --output-file page.html "https://example.com"
```

**Convenience options:** `--preset` applies common option sets (only when you don’t set those options): `screenshot`, `screenshot-and-html` (HTML + full-page screenshot in JSON), `fetch` (`--render-js false` for file download), `extract-links` / `extract-emails` / `extract-phones` (extract-rules; response = extracted JSON only), `scroll-page` (infinite_scroll JS scenario). For long JSON use shell: `--js-scenario "$(cat file.json)"`. `--force-extension ext` forces the output file extension. Run `scrapingbee scrape --help` for grouped options.

## Sub-pages (open only what you need)

- **Params:** [reference/scrape/options.md](reference/scrape/options.md) — render-js, wait, proxies, headers, cookies, response format, screenshots, device, timeout, POST/PUT.
- **Extraction:** [reference/scrape/extraction.md](reference/scrape/extraction.md) — extract-rules (CSS/XPath), ai-query, ai-extract-rules.
- **JS scenario:** [reference/scrape/js-scenario.md](reference/scrape/js-scenario.md) — click, scroll, fill, wait, infinite_scroll.
- **Strategies:** [reference/scrape/strategies.md](reference/scrape/strategies.md) — file fetch (render-js false), cheap (no JS), LLM text (markdown/text), structured extraction.
- **Proxy blocked:** [reference/proxy/strategies.md](reference/proxy/strategies.md) — premium → stealth.
- **Output:** [reference/scrape/output.md](reference/scrape/output.md) — raw body vs json_response, screenshot.

Batch: `--input-file urls.txt` and `--output-dir`; see [reference/batch/overview.md](reference/batch/overview.md). **Crawl:** same scrape options; see [reference/crawl/overview.md](reference/crawl/overview.md).
