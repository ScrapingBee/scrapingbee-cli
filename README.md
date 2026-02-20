# ScrapingBee CLI

A command-line client for the [ScrapingBee](https://www.scrapingbee.com/) API. Use it to scrape web pages, run search (Google, Fast Search, Amazon, Walmart, YouTube), and call the ChatGPT endpoint from the terminal.

## Requirements

- **Python 3.8+**

## Installation

### Using pip (recommended)

```bash
pip install scrapingbee-cli
```

Then run:

```bash
scrapingbee --help
```

### Using a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install scrapingbee-cli
scrapingbee usage
```

### Using pipx (isolated CLI)

```bash
pipx install scrapingbee-cli
```

### From source

```bash
git clone https://github.com/scrapingbee/scrapingbee-cli.git
cd scrapingbee-cli
pip install -e .
```

## Configuration

You need a ScrapingBee API key. Provide it in one of these ways:

1. **Environment variable** (recommended):

   ```bash
   export SCRAPINGBEE_API_KEY=your_api_key_here
   ```

2. **Flag** on every command:

   ```bash
   scrapingbee --api-key=your_api_key_here usage
   ```

Get your API key from the [ScrapingBee dashboard](https://app.scrapingbee.com/).

## Usage

```bash
scrapingbee [command] [arguments] [flags]
```

**Global flags:**

| Flag        | Short | Description                                      |
|-------------|-------|--------------------------------------------------|
| `--api-key` |       | ScrapingBee API key (or set `SCRAPINGBEE_API_KEY`) |
| `--output`  | `-o`  | Write response to a file instead of stdout       |
| `--verbose` | `-v`  | Print HTTP status, cost, and response headers    |
| `--batch-output-dir` | | Batch mode: folder for output files (default: `batch_<timestamp>` in current directory) |
| `--concurrency` | | Batch mode: max concurrent requests (0 = use limit from usage API; if set, must not exceed your plan limit) |

Run `scrapingbee --help` or `scrapingbee [command] --help` for details.

## Batch mode

All commands that take a single input (URL, query, ASIN, product ID, video ID, or prompt) support **batch mode** via `--input-file`:

- Provide a file with **one input per line** (empty lines are skipped).
- The CLI calls the ScrapingBee **usage** API to get your **max concurrent request limit** and runs that many requests in parallel.
- **Output:** One file per response is written to a folder. Successful responses go to `1.txt`, `2.txt`, … (by input order). Failed items are reported on stderr and, if the API returned a body, written to `N.err`.
- **Output folder:** Use `--batch-output-dir` to set a custom folder. If omitted, a folder named `batch_<YYYYMMDD_HHMMSS>` is created in the current directory.
- **Concurrency:** Use `--concurrency N` to cap concurrent requests. If omitted (or 0), the CLI uses your plan limit from the usage API. If you set `--concurrency` higher than your plan limit, the batch is not run and you get an error (check limits with `scrapingbee usage`).
- **Credits:** Before running, the CLI checks the usage API for available credits. If the response includes a credit balance and it is less than the number of batch items, the batch is not run and you are informed (run `scrapingbee usage` to see your balance).
- When finished, the CLI prints to **stdout**: `Batch complete. Output written to <absolute path>`.
- You cannot use `--input-file` together with a positional argument.

**Example: scrape many URLs**

```bash
# urls.txt contains one URL per line; output in ./my_batch (or default batch_<timestamp>)
scrapingbee scrape --input-file urls.txt --batch-output-dir my_batch
# When done: "Batch complete. Output written to /path/to/my_batch"
```

**Example: run many Google searches**

```bash
scrapingbee google --input-file queries.txt --country-code=us
```

**Example: fetch many Amazon products by ASIN**

```bash
scrapingbee amazon-product --input-file asins.txt --domain=com
```

**Supported commands and input type:**

| Command | Input per line |
|---------|----------------|
| `scrape` | URL |
| `google` | Search query |
| `fast-search` | Search query |
| `amazon-product` | ASIN |
| `amazon-search` | Search query |
| `walmart-search` | Search query |
| `walmart-product` | Product ID |
| `youtube-search` | Search query |
| `youtube-metadata` | Video ID |
| `youtube-transcript` | Video ID |
| `youtube-trainability` | Video ID |
| `chatgpt` | Prompt (one per line) |

## Commands

| Command               | Description                                      |
|-----------------------|--------------------------------------------------|
| `usage`               | Check API credit usage and concurrency           |
| `scrape [url]`        | Scrape a URL with the HTML API (JS, proxies, etc.) |
| `google [query]`      | Google Search API (structured JSON)             |
| `fast-search [query]` | Fast Search API (sub-second SERP results)       |
| `amazon-product [ASIN]` | Fetch Amazon product details by ASIN          |
| `amazon-search [query]` | Search Amazon products                         |
| `walmart-search [query]` | Search Walmart products                      |
| `walmart-product [id]`  | Fetch Walmart product details by product ID   |
| `youtube-search [query]` | Search YouTube videos                        |
| `youtube-metadata [video-id]` | Fetch YouTube video metadata              |
| `youtube-transcript [video-id]` | Fetch YouTube video transcript/captions  |
| `youtube-trainability [video-id]` | Check if a video transcript is available for training |
| `chatgpt [prompt]`    | Send a prompt to the ChatGPT API                |

## Examples

**Check credits:**

```bash
scrapingbee usage
```

**Scrape a page (basic):**

```bash
scrapingbee scrape "https://example.com"
```

**Scrape with options (no JS, save to file, verbose):**

```bash
scrapingbee scrape "https://example.com" --render-js=false -o page.html -v
```

**Google search:**

```bash
scrapingbee google "pizza new york" --country-code=us
```

**Fast search (sub-second):**

```bash
scrapingbee fast-search "ai news today" --country-code=us --language=en
```

**Amazon product by ASIN:**

```bash
scrapingbee amazon-product B0DPDRNSXV --domain=com
```

**Amazon search:**

```bash
scrapingbee amazon-search "laptop" --domain=com --sort-by=bestsellers
```

**Walmart search (min/max price are integers):**

```bash
scrapingbee walmart-search "headphones" --min-price=20 --max-price=100
```

**YouTube video metadata:**

```bash
scrapingbee youtube-metadata dQw4w9WgXcQ
```

**ChatGPT:**

```bash
scrapingbee chatgpt "Explain quantum computing in one sentence"
```

## Output

- By default, the raw API response (usually JSON or HTML) is printed to stdout.
- Use `-o file` or `--output file` to write to a file.
- Use `-v` or `--verbose` to print HTTP status, credit cost (`Spb-Cost`), and other headers to stderr before the body.

## Command parameters

Each command supports the global flags (`--api-key`, `-o`, `-v`, `--batch-output-dir`, `--concurrency`) plus the parameters below. Boolean flags accept `true`/`false` (e.g. `--render-js=false`). All commands that take a single input also support **`--input-file`** for batch mode; use **`--batch-output-dir`** and **`--concurrency`** as needed (see [Batch mode](#batch-mode)).

### `usage`

No parameters (only global flags).

---

### `scrape [url]`

| Parameter | Short | Type | Description |
|-----------|-------|------|--------------|
| `--input-file` | | string | Batch: file with one URL per line (max concurrency from usage API) |
| `--render-js` | | string | Enable/disable JS rendering (true/false, default: true) |
| `--js-scenario` | | string | JSON JavaScript scenario to execute |
| `--wait` | | int | Wait time in ms before returning HTML (0–35000) |
| `--wait-for` | | string | CSS/XPath selector to wait for before returning |
| `--wait-browser` | | string | Browser wait (domcontentloaded\|load\|networkidle0\|networkidle2) |
| `--block-ads` | | string | Block ads (true/false) |
| `--block-resources` | | string | Block images and CSS (true/false) |
| `--window-width` | | int | Viewport width in pixels |
| `--window-height` | | int | Viewport height in pixels |
| `--premium-proxy` | | string | Use premium/residential proxies (true/false) |
| `--stealth-proxy` | | string | Use stealth proxies (true/false) |
| `--country-code` | | string | Proxy country code (ISO 3166-1) |
| `--own-proxy` | | string | Use your own proxy (user:pass@host:port) |
| `--forward-headers` | | string | Forward custom headers (true/false) |
| `--forward-headers-pure` | | string | Forward only custom headers (true/false) |
| `--header` | `-H` | strings | Custom header (Key:Value), repeatable |
| `--json-response` | | string | Return JSON response (true/false) |
| `--screenshot` | | string | Take screenshot (true/false) |
| `--screenshot-selector` | | string | CSS selector for screenshot area |
| `--screenshot-full-page` | | string | Full page screenshot (true/false) |
| `--return-page-source` | | string | Return unaltered HTML (true/false) |
| `--return-markdown` | | string | Return markdown content (true/false) |
| `--return-text` | | string | Return plain text (true/false) |
| `--extract-rules` | | string | CSS/XPath extraction rules (JSON string) |
| `--ai-query` | | string | AI extraction query (natural language) |
| `--ai-selector` | | string | CSS selector to focus AI extraction |
| `--ai-extract-rules` | | string | AI extraction rules (JSON string) |
| `--session-id` | | int | Session ID for sticky IP (0–10000000) |
| `--timeout` | | int | Timeout in ms (1000–140000) |
| `--cookies` | | string | Custom cookies string |
| `--device` | | string | Device type (desktop\|mobile) |
| `--custom-google` | | string | Enable Google scraping (true/false) |
| `--transparent-status-code` | | string | Transparent HTTP status code (true/false) |
| `--scraping-config` | | string | Pre-saved scraping configuration name |
| `--method` | `-X` | string | HTTP method (GET\|POST\|PUT) |
| `--data` | `-d` | string | Request body for POST/PUT |
| `--content-type` | | string | Content-Type header for POST/PUT |

---

### `google [query]`

| Parameter | Type | Description |
|-----------|------|-------------|
| `--search-type` | string | classic\|news\|maps\|lens\|shopping\|images\|ai_mode |
| `--country-code` | string | Country code (ISO 3166-1) |
| `--device` | string | desktop\|mobile |
| `--page` | int | Page number |
| `--language` | string | Language code (e.g. en, fr, de) |
| `--nfpr` | string | Disable autocorrection (true/false) |
| `--extra-params` | string | Extra URL parameters (URL-encoded) |
| `--add-html` | string | Include full HTML in response (true/false) |
| `--light-request` | string | Light request mode (true/false) |

---

### `fast-search [query]`

| Parameter | Type | Description |
|-----------|------|-------------|
| `--page` | int | Page number (default: 1) |
| `--country-code` | string | Country code (ISO 3166-1) |
| `--language` | string | Language code (e.g. en, fr) |

---

### `amazon-product [ASIN]`

| Parameter | Type | Description |
|-----------|------|-------------|
| `--device` | string | desktop\|mobile\|tablet |
| `--domain` | string | Amazon domain (com\|co.uk\|de\|fr\|...) |
| `--country` | string | Country code (us\|gb\|de\|...) |
| `--zip-code` | string | ZIP code for local results |
| `--language` | string | Language code (e.g. en_US, es_US, fr_FR) |
| `--currency` | string | Currency code (USD\|EUR\|GBP\|...) |
| `--add-html` | string | Include full HTML (true/false) |
| `--light-request` | string | Light request (true/false) |
| `--screenshot` | string | Take screenshot (true/false) |

---

### `amazon-search [query]`

| Parameter | Type | Description |
|-----------|------|-------------|
| `--start-page` | int | Starting page number |
| `--pages` | int | Number of pages to fetch |
| `--sort-by` | string | most_recent\|price_low_to_high\|price_high_to_low\|average_review\|bestsellers\|featured |
| `--device` | string | desktop\|mobile\|tablet |
| `--domain` | string | Amazon domain (com\|co.uk\|de\|...) |
| `--country` | string | Country code |
| `--zip-code` | string | ZIP code |
| `--language` | string | Language code (e.g. en_US, es_US, fr_FR) |
| `--currency` | string | Currency code |
| `--category-id` | string | Amazon category ID |
| `--merchant-id` | string | Merchant/seller ID |
| `--autoselect-variant` | string | Auto-select variants (true/false) |
| `--add-html` | string | Include full HTML (true/false) |
| `--light-request` | string | Light request (true/false) |
| `--screenshot` | string | Take screenshot (true/false) |

---

### `walmart-search [query]`

| Parameter | Type | Description |
|-----------|------|-------------|
| `--min-price` | int | Minimum price filter |
| `--max-price` | int | Maximum price filter |
| `--sort-by` | string | best_match\|price_low\|price_high\|best_seller |
| `--device` | string | desktop\|mobile\|tablet |
| `--domain` | string | Walmart domain |
| `--fulfillment-speed` | string | today\|tomorrow\|2_days\|anytime |
| `--fulfillment-type` | string | Fulfillment type (in_store) |
| `--delivery-zip` | string | Delivery ZIP code |
| `--store-id` | string | Walmart store ID |
| `--add-html` | string | Include full HTML (true/false) |
| `--light-request` | string | Light request (true/false) |
| `--screenshot` | string | Take screenshot (true/false) |

---

### `walmart-product [product-id]`

| Parameter | Type | Description |
|-----------|------|-------------|
| `--domain` | string | Walmart domain |
| `--delivery-zip` | string | Delivery ZIP code |
| `--store-id` | string | Walmart store ID |
| `--add-html` | string | Include full HTML (true/false) |
| `--light-request` | string | Light request (true/false) |
| `--screenshot` | string | Take screenshot (true/false) |

---

### `youtube-search [query]`

| Parameter | Type | Description |
|-----------|------|-------------|
| `--upload-date` | string | today\|last_hour\|this_week\|this_month\|this_year |
| `--type` | string | video\|channel\|playlist\|movie |
| `--duration` | string | Duration filter: under 4 min, 4–20 min, over 20 min |
| `--sort-by` | string | relevance\|rating\|view_count\|upload_date |
| `--hd` | string | HD only (true/false) |
| `--4k` | string | 4K only (true/false) |
| `--subtitles` | string | With subtitles (true/false) |
| `--creative-commons` | string | Creative Commons only (true/false) |
| `--live` | string | Live streams only (true/false) |
| `--360` | string | 360° videos only (true/false) |
| `--3d` | string | 3D videos only (true/false) |
| `--hdr` | string | HDR videos only (true/false) |
| `--location` | string | With location (true/false) |
| `--vr180` | string | VR180 only (true/false) |

---

### `youtube-metadata [video-id]`

No parameters (only global flags).

---

### `youtube-transcript [video-id]`

| Parameter | Type | Description |
|-----------|------|-------------|
| `--language` | string | Transcript language (e.g. en, es, fr) |
| `--transcript-origin` | string | auto_generated\|uploader_provided |

---

### `youtube-trainability [video-id]`

No parameters (only global flags).

---

### `chatgpt [prompt]`

No parameters; the prompt is the positional argument (or multiple words joined). Only global flags apply.

---

## Project structure

```
scrapingbee-cli/
├── pyproject.toml           # Package config and dependencies
├── src/
│   └── scrapingbee_cli/    # Python package
│       ├── __init__.py
│       ├── cli.py           # Click commands (scrape, google, amazon, etc.)
│       ├── client.py        # HTTP client and API request builders
│       ├── config.py        # API key and base URL
│       └── batch.py         # Batch mode helpers
└── README.md
```

## Documentation

- [ScrapingBee API documentation](https://www.scrapingbee.com/documentation/)
