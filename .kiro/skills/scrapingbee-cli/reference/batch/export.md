# Export & Resume

## Export batch/crawl output

Merge all numbered output files from a batch or crawl into a single stream for downstream processing.

```bash
scrapingbee export --output-file all.ndjson --input-dir batch_20250101_120000
scrapingbee export --output-file pages.txt --input-dir crawl_20250101 --format txt
scrapingbee export --output-file results.csv --input-dir serps/ --format csv
# Output only items that changed since last run:
scrapingbee export --input-dir new_batch/ --diff-dir old_batch/ --format ndjson
```

| Parameter | Description |
|-----------|-------------|
| `--input-dir` | (Required) Batch or crawl output directory. |
| `--format` | `ndjson` (default), `txt`, or `csv`. |
| `--diff-dir` | Previous batch/crawl directory. Only output items whose content changed or is new (unchanged items are skipped by MD5 comparison). |

**ndjson output:** Each line is one JSON object. JSON files are emitted as-is; HTML/text/markdown files are wrapped in `{"content": "..."}`. If a `manifest.json` is present (written by batch or crawl), a `_url` field is added to each record with the source URL.

**txt output:** Each block starts with `# URL` (when manifest is present), followed by the page content.

**csv output:** Flattens JSON files into tabular rows. For API responses that contain a list (e.g. `organic_results`, `products`, `results`), each list item becomes a row. For single-object responses (e.g. a product page), the object itself is one row. Nested dicts/arrays are serialised as JSON strings. Non-JSON files are skipped. `_url` column is added when `manifest.json` is present. Ideal for SERP results, Amazon/Walmart product searches, and YouTube metadata batches.

**manifest.json (batch and crawl):** Both `scrape` batch runs and `crawl` now write `manifest.json` to the output directory. Format: `{"<input>": {"file": "N.ext", "fetched_at": "<ISO-8601 UTC>", "http_status": 200, "credits_used": 5, "latency_ms": 1234, "content_md5": "<md5>"}}`. Fields `credits_used` (from `Spb-Cost` header, `null` for SERP endpoints), `latency_ms` (request latency in ms), and `content_md5` (MD5 of body, used by `--diff-dir`) are included. When `--diff-dir` detects unchanged content, entries have `"file": null` and `"unchanged": true`. Useful for time-series analysis, audit trails, and monitoring workflows. The `export` command reads both old (plain string values) and new (dict values) manifest formats.

## Resume an interrupted batch

Stop and restart a batch without re-processing completed items:

```bash
# Initial run (stopped partway through)
scrapingbee scrape --output-dir my-batch --input-file urls.txt

# Resume: skip already-saved items
scrapingbee scrape --output-dir my-batch --resume --input-file urls.txt
```

`--resume` scans `--output-dir` for existing `N.ext` files and skips those item indices. Works with all batch commands: `scrape`, `google`, `fast-search`, `amazon-product`, `amazon-search`, `walmart-search`, `walmart-product`, `youtube-search`, `youtube-metadata`, `chatgpt`.

**Requirements:** `--output-dir` must point to the folder from the previous run. Items with only `.err` files are not skipped (they failed and will be retried).

## Resume an interrupted crawl

```bash
# Initial run (stopped partway through)
scrapingbee crawl --output-dir my-crawl "https://example.com"

# Resume: skip already-crawled URLs
scrapingbee crawl --output-dir my-crawl --resume "https://example.com"
```

Resume reads `manifest.json` from the output dir to pre-populate the set of seen URLs and the file counter. Works with URL-based crawl and sitemap crawl. See [reference/crawl/overview.md](reference/crawl/overview.md).
