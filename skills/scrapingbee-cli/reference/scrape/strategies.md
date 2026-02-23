# Scrape: strategies

When to use which options. Proxy escalation (blocked/403/429): [reference/proxy/strategies.md](reference/proxy/strategies.md).

## Fetching files or images

Use **`--preset fetch`** or **`--render-js false`** when the URL returns a file (PDF, image, ZIP). Raw bytes, 1 credit. **Limit: 2 MB per request.** Screenshot of a webpage = `--screenshot true` (needs JS, 5 credits). Use space-separated values only (e.g. `--render-js false`), not `=value`.

```bash
scrapingbee --output-file doc.pdf scrape "https://example.com/doc.pdf" --preset fetch
# or: scrapingbee --output-file doc.pdf scrape "https://example.com/doc.pdf" --render-js false
```

## Cheaper / no JavaScript

If the page doesn't need JS: **`--render-js false`** → 1 credit instead of 5.

## Clean text for LLMs

**`--return-page-markdown true`** or **`--return-page-text true`** for main content as markdown or plain text instead of HTML.

## Structured data extraction

**`--extract-rules`** (CSS/XPath) or **`--ai-query`** / **`--ai-extract-rules`** (+5 credits). See [reference/scrape/extraction.md](reference/scrape/extraction.md).

| Goal | Option |
|------|--------|
| File/image download | `--render-js false` |
| Lower cost (no JS) | `--render-js false` |
| Blocked / 403 / 429 | [reference/proxy/strategies.md](reference/proxy/strategies.md) |
| Text for LLMs | `--return-page-markdown true` or `--return-page-text true` |
| Structured JSON | [reference/scrape/extraction.md](reference/scrape/extraction.md) |
