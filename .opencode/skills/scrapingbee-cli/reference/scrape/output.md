# Scrape output

**Default (no `--json-response`):** Raw body (HTML, markdown, text, or PNG). With `--extract-rules`: body = extracted JSON. With `--screenshot` only: body = raw PNG.

**With `--json-response true`:** JSON object. Keys: `headers`, `cost`, `initial-status-code`, `resolved-url`, `type`, `body` (or `content` for markdown/text). When used: `screenshot` (base64 PNG; only if `--screenshot true` and json_response; decode for image; HTML in `body`), `cookies`, `evaluate_results` (from js-scenario evaluate; not with stealth), `js_scenario_report`, `iframes`, **`xhr`** (internal requests; use to inspect XHR/fetch), `metadata`. Extract rules + json_response: `body` = extracted object. **Limit:** 2 MB per request for file/image. Use space-separated values only (e.g. `--json-response true`), not `=value`.

**With `--chunk-size N`:** NDJSON output — one JSON object per line. Each object: `{"url":"…","chunk_index":0,"total_chunks":3,"content":"…","fetched_at":"…"}`. Combine with `--return-page-markdown true` or `--return-page-text true` for clean text chunks ready for vector DB / LLM ingestion. Extension forced to `.ndjson` in batch mode.
