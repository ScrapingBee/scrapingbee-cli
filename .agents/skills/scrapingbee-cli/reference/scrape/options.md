# Scrape: parameters

Scrape (and crawl URL-mode) options. Extraction: [reference/scrape/extraction.md](reference/scrape/extraction.md). JS scenario: [reference/scrape/js-scenario.md](reference/scrape/js-scenario.md). Output: [reference/scrape/output.md](reference/scrape/output.md). In the CLI, `scrapingbee scrape --help` shows these grouped (Rendering, Proxy, Headers, Output, Screenshot, Extraction, Request).

## Presets and JS scenario

| Parameter | Type | Description |
|-----------|------|-------------|
| `--preset` | see below | Apply common option set. Preset only sets options you did not set. |
| `--force-extension` | string | Force output file extension (e.g. html, json). Used when `--output-file` has no extension. |

For long JSON (`--js-scenario`, `--extract-rules`) use shell: `--js-scenario "$(cat scenario.json)"`.

**Preset values and params they set (when not already set):**

| Preset | Params set |
|--------|------------|
| `screenshot` | `--screenshot true`, `--render-js true` |
| `screenshot-and-html` | `--json-response true`, `--screenshot true`, `--screenshot-full-page true`, `--render-js true` (output: JSON with HTML in `body` and full-page screenshot in `screenshot`) |
| `fetch` | `--render-js false` (for fetching/downloading files; no JS rendering) |
| `extract-links` | `--extract-rules` = all `a` hrefs as list. Raw body = extracted JSON only (no wrapper). |
| `extract-emails` | `--extract-rules` = mailto links as list. Raw body = extracted JSON only (no wrapper). |
| `extract-phones` | `--extract-rules` = tel links as list. Raw body = extracted JSON only (no wrapper). |
| `scroll-page` | `--js-scenario` = infinite_scroll (full page), `--render-js true` |

**File fetching:** Use `--preset fetch` or `--render-js false` when the goal is to download files (e.g. PDF, images). Use space-separated values only (e.g. `--render-js false`), not `=value`.

## Rendering and wait

| Parameter | Type | Description |
|-----------|------|-------------|
| `--render-js` | true/false | Headless JS. When omitted, not sent (API default may apply). |
| `--wait` | int | Wait ms (0–35000) after load. |
| `--wait-for` | string | CSS or XPath selector; return after element appears. `/` prefix = XPath. |
| `--wait-browser` | string | `domcontentloaded`, `load`, `networkidle0`, `networkidle2`. |
| `--js-scenario` | string | JSON browser instructions. See [reference/scrape/js-scenario.md](reference/scrape/js-scenario.md). |

## Viewport, blocking, proxies

| Parameter | Type | Description |
|-----------|------|-------------|
| `--window-width` / `--window-height` | int | Viewport (px). |
| `--block-ads` / `--block-resources` | true/false | Block ads or images/CSS. |
| `--premium-proxy` / `--stealth-proxy` | true/false | Premium or stealth (75 credits; JS required). |
| `--country-code` | string | ISO 3166-1 (e.g. us, de). Use with premium/stealth. |
| `--own-proxy` | string | `user:pass@host:port`. |
| `--session-id` | int | Sticky IP ~5 min (0–10000000). |

Blocked? See [reference/proxy/strategies.md](reference/proxy/strategies.md).

## Headers and cookies

| Parameter | Type | Description |
|-----------|------|-------------|
| `-H` / `--header` | Key:Value | Custom header (repeatable). For GET sent as Spb-* to ScrapingBee; for POST/PUT forwarded as-is (e.g. Content-Type). |
| `--forward-headers` / `--forward-headers-pure` | true/false | Forward headers; pure = only yours (use with `--render-js false`). Pass as `--option true` or `--option false` (space-separated). |
| `--cookies` | string | `name=value,domain=example.com;name2=value2,path=/`. |

## Response and screenshots

| Parameter | Type | Description |
|-----------|------|-------------|
| `--return-page-source` / `--return-page-markdown` / `--return-page-text` | true or false (separate arg, e.g. `--return-page-text true`) | Raw HTML, markdown, or plain text. |
| `--json-response` | true/false | Wrap in JSON (body, headers, cost, screenshot if used). See [reference/scrape/output.md](reference/scrape/output.md). |
| `--screenshot` / `--screenshot-full-page` / `--screenshot-selector` | true/false or string | Viewport, full page, or CSS selector region. |

## Other

| Parameter | Type | Description |
|-----------|------|-------------|
| `--device` | desktop \| mobile | Device type (CLI validates). |
| `--timeout` | int | Timeout ms (1000–140000). Scrape job timeout on ScrapingBee. The CLI sets the HTTP client (aiohttp) timeout to this value in seconds plus 30 s (for send/receive) so the client does not give up before the API responds. |
| `--custom-google` / `--transparent-status-code` | — | Google (15 credits), target status. |
| `-X` / `-d` | — | Method (GET, POST, or PUT), body for POST/PUT. The request **to ScrapingBee** is always `application/x-www-form-urlencoded`; use form body (e.g. `KEY_1=VALUE_1`). For POST/PUT use **`--render-js false`** so the request is forwarded without the browser tunnel. |

## Retries (global)

Global `--retries` and `--backoff` apply to scrape and other commands. Retries apply on 5xx or connection/timeout errors with exponential backoff.
