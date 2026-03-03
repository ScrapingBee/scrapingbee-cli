# Troubleshooting

Decision tree for common ScrapingBee CLI issues.

## Empty response / blank body

1. **Page requires JavaScript?** Add `--render-js true`.
2. **Dynamic content not loaded?** Add `--wait 3000` or `--wait-for "#content"`.
3. **Behind login / bot check?** Try `--stealth-proxy true`. See [reference/proxy/strategies.md](reference/proxy/strategies.md).

## 403 / 429 / blocked / CAPTCHA

Escalate through proxy tiers. See [reference/proxy/strategies.md](reference/proxy/strategies.md):

1. Default (no proxy flag) → `--premium-proxy true` → `--stealth-proxy true`
2. Geo-restrict: add `--country-code us` (or target country).
3. Still failing: contact ScrapingBee support — some sites require custom handling.

## N.err files in batch output

Each `.err` file has the error message on the first line, then the raw API response body (if any).

- **Timeout errors** (`asyncio.TimeoutError` / `aiohttp.ServerTimeoutError`): Increase `--retries 5`. The target page is slow — add `--timeout 90000` to give it 90 s.
- **HTTP 500 from API**: Transient — retry. Add `--retries 5 --backoff 3.0`.
- **HTTP 4xx from target** (403, 404): URL is blocked or doesn't exist. Try `--premium-proxy true`.
- **Resume after partial failure**: Rerun with `--resume --output-dir <same folder>` — already-saved items are skipped.

## Crawl stopped early / fewer pages than expected

- **JavaScript navigation** (React/Vue SPAs): Add `--render-js true`.
- **Max depth reached**: Increase `--max-depth` or set `--max-depth 0` for unlimited.
- **Max pages reached**: Increase `--max-pages` or set `--max-pages 0`.
- **Interrupted crawl**: Rerun with `--resume --output-dir <previous crawl folder>`.
- **Links not found**: The page uses a non-standard link format. Check whether `--return-page-markdown true` or `--json-response true` is needed.

## ai-query returns null or unexpected value

1. **Narrow scope**: Add `--ai-selector "#product-price"` to focus on the right element.
2. **Rephrase**: Be explicit — `"price in USD as a number"` instead of `"price"`.
3. **Verify page content first**: Run without `--ai-query` and inspect the HTML to confirm the data is present.
4. **Try `--ai-extract-rules`**: Define a schema with type hints — `{"price":{"description":"price in USD","type":"number"}}` — for more reliable extraction.

## Output file not written

- Global `--output-file` must come **before** the subcommand:
  `scrapingbee scrape --output-file out.html URL` ✓
  `scrapingbee scrape URL --output-file out.html` ✗

- For batch, use `--output-dir`:
  `scrapingbee scrape --output-dir results --input-file urls.txt`

## Why use ScrapingBee instead of WebFetch or curl?

ScrapingBee automatically rotates proxies, handles CAPTCHAs, and renders JavaScript. Direct requests fail on most real websites. See [reference/scrape/strategies.md](reference/scrape/strategies.md).

## Credits lower than expected

Run `scrapingbee usage` to see current balance and concurrency limit. Credits deducted per request:

| Feature | Credits |
|---------|---------|
| Default (JS on) | 5 |
| `--render-js false` | 1 |
| `--premium-proxy true` | 25 |
| `--stealth-proxy true` | 75 |
| `--ai-query` / `--ai-extract-rules` | +5 |
| Google Search | 10–15 |
| Amazon / Walmart | 5–15 |
| YouTube | 5 |
| ChatGPT | 15 |
