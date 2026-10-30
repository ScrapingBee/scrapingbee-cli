# Patterns and recipes

Common multi-step workflows and how to run them with the CLI.

## Crawl then extract / summarize (crawl + AI)

**Goal:** Crawl a site, then run AI extraction or summarization on the discovered URLs.

**Option A — Crawl with AI in one go:** Use `scrapingbee crawl` with `--ai-query` (or `--extract-rules`). The crawler saves the AI/JSON response per page and **automatically discovers links** by fetching each URL as HTML when the main response has no links. One command; each page is fetched twice (once for your output, once for link discovery).

```bash
scrapingbee crawl "https://example.com" --ai-query "Summarize this page in 2 sentences" --output-dir ./crawl_out --max-pages 50
```

**Option B — Crawl first, then batch AI:** (1) Extract a URL list from the start page. (2) Run batch scrape with `--ai-query` (or `--extract-rules`) on that list. Use when you want to separate “discover URLs” from “extract/summarize”, re-run extraction with different prompts without re-crawling, or process only a curated subset of URLs.

```bash
# Step 1: Extract all links from the start page into a file
scrapingbee scrape --output-file links.json “https://example.com” --preset extract-links

# Step 2: Pick the URLs you want (edit links.json → urls.txt, one URL per line), then batch AI
scrapingbee scrape --output-dir ./summaries --input-file urls.txt --ai-query “Summarize in 3 bullet points”
```

> **Tip:** The crawl command writes `manifest.json` (URL → filename map) to the output directory. Use `scrapingbee export --input-dir crawl_out --format ndjson` to merge crawl output into a single NDJSON stream with `_url` fields. See [reference/batch/export.md](reference/batch/export.md).

**When to use which:** Option A is simpler (one command, follows links automatically). Option B gives you a reusable, curated URL list and lets you re-run extraction with different prompts without re-crawling.

## SERP → scrape result pages

**Goal:** Search Google (or Fast Search), then scrape the actual pages from the results.

```bash
# Step 1: Run the search and extract organic result URLs in one command (no jq needed)
scrapingbee google --extract-field organic_results.url "best python web scraping libraries" > urls.txt

# Step 2: Batch scrape each result page as Markdown text
scrapingbee scrape --output-dir pages --input-file urls.txt --return-page-markdown true

# Optional: export all pages to a single file for LLM processing
scrapingbee export --output-file all.ndjson --input-dir pages
```

For many queries at once, use `--input-file queries.txt google` to run all searches in batch first, then extract and scrape.

> **`--extract-field`** outputs one value per line, making it directly pipeable into `--input-file`. Supports dot-notation to arbitrary depth: `key`, `key.subkey`, `key.subkey.deeper`, etc. When a path segment hits a list, the remaining path is applied to every item.

## Amazon search → product details

**Goal:** Search for products, then fetch full details for each result by ASIN.

```bash
# One command: search and extract ASINs directly (no jq)
scrapingbee amazon-search --extract-field products.asin "mechanical keyboard tenkeyless" > asins.txt

# Batch fetch full product details for each ASIN
scrapingbee amazon-product --output-dir products --input-file asins.txt

# Export to CSV for spreadsheet analysis
scrapingbee export --output-file products.csv --input-dir products --format csv
```

> Use `--fields asin,title,price,rating` on the final export to narrow the columns, or `--extract-field products.url` if you want to scrape the Amazon product pages directly.

## Walmart search → product details

**Goal:** Search for Walmart products, then fetch full details for each result by product ID.

```bash
# One command: search and extract product IDs directly (no jq)
scrapingbee walmart-search --extract-field products.id "mechanical keyboard" > ids.txt

# Batch fetch full product details for each ID
scrapingbee walmart-product --output-dir products --input-file ids.txt

# Export to CSV for spreadsheet analysis
scrapingbee export --output-file products.csv --input-dir products --format csv
```

> Use `--fields id,title,price,rating` on the search to narrow the initial output.

## YouTube search → video metadata

**Goal:** Search for videos, then fetch full metadata for each result.

```bash
# One command: search and extract video links (no jq or sed needed)
scrapingbee youtube-search --extract-field results.link "python asyncio tutorial" > videos.txt

# Batch fetch metadata — full YouTube URLs are accepted automatically
scrapingbee youtube-metadata --output-dir metadata --input-file videos.txt

# Export to CSV
scrapingbee export --output-file videos.csv --input-dir metadata --format csv
```

> `youtube-metadata` accepts full YouTube URLs (`https://www.youtube.com/watch?v=...`) as well as bare video IDs — no manual ID extraction needed.

## Batch SERP for many queries

**Goal:** Run many search queries at once.

```bash
# One query per line in queries.txt
scrapingbee google --output-dir ./serps --input-file queries.txt
# Output: ./serps/1.json, 2.json, … (SERP JSON per query)

# Export all results to CSV
scrapingbee export --output-file serps.csv --input-dir serps --format csv
```

## Scrape one URL with a preset

**Goal:** Quick screenshot, or “fetch” (no JS), or extract links/emails without writing selectors.

```bash
scrapingbee scrape "https://example.com" --preset screenshot
scrapingbee scrape "https://example.com" --preset fetch
scrapingbee scrape "https://example.com" --preset extract-links
```

See [reference/scrape/overview.md](reference/scrape/overview.md) and `scrapingbee scrape --help` for `--preset` values.

## Refreshing data (--update-csv)

**Goal:** Re-fetch data for all items in a CSV and update the file in-place with fresh results.

```bash
# Fetch fresh data and update the CSV in-place
scrapingbee scrape --input-file products.csv --input-column url --update-csv

# Or for Amazon products
scrapingbee amazon-product --input-file asins.csv --input-column asin --update-csv
```

`manifest.json` written by every batch includes `fetched_at` (ISO-8601 UTC), `http_status`, `credits_used`, and `latency_ms` per item, enabling time-series tracking.

## Price monitoring (scheduled)

**Goal:** Track Amazon/Walmart product prices automatically with scheduled refreshes.

```bash
# Create a CSV with one ASIN per line
cat > asins.csv <<EOF
asin
B0DPDRNSXV
B09G9FPHY6
B0B5HJWWD1
EOF

# Register a daily cron job that refreshes the CSV in-place
scrapingbee schedule --every 1d --name prices \
  amazon-product --input-file asins.csv --input-column asin --update-csv --domain com
```

### List and manage schedules

```bash
# View active schedules
scrapingbee schedule --list

# Stop a specific schedule
scrapingbee schedule --stop prices

# Stop all schedules
scrapingbee schedule --stop all
```

## Automated pipelines (subagent)

For hands-free multi-step execution, install the pipeline subagent into your project:

```bash
cp skills/scrapingbee-cli/.claude/agents/scraping-pipeline.md .claude/agents/
```

Claude will then delegate full pipelines — search → extract → batch → export — to an isolated subagent that checks credits, handles errors, and returns a summary without flooding the main conversation context.

## Where to look next

- **Crawl options:** [reference/crawl/overview.md](reference/crawl/overview.md)
- **Scrape extraction (AI, rules):** [reference/scrape/extraction.md](reference/scrape/extraction.md)
- **Batch (input-file, output-dir):** [reference/batch/overview.md](reference/batch/overview.md)
- **Credits / limits:** [reference/usage/overview.md](reference/usage/overview.md)
