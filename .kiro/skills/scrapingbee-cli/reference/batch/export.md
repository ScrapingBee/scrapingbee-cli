# Export & Resume

## Export batch/crawl output

Merge all numbered output files from a batch or crawl into a single stream for downstream processing.

```bash
scrapingbee export --output-file all.ndjson --input-dir batch_20250101_120000
scrapingbee export --output-file pages.txt --input-dir crawl_20250101 --format txt
scrapingbee export --output-file results.csv --input-dir serps/ --format csv --flatten
scrapingbee export --output-file results.csv --input-dir products/ --format csv --flatten --columns "title,price,rating"
```

| Parameter | Description |
|-----------|-------------|
| `--input-dir` | (Required) Batch or crawl output directory. |
| `--format` | `ndjson` (default), `txt`, or `csv`. |
| `--flatten` | CSV: recursively flatten nested dicts to dot-notation columns. |
| `--flatten-depth` | int | CSV: max nesting depth for `--flatten` (default: 5). Use higher values for deeply nested data. |
| `--columns` | CSV: comma-separated column names to include. Rows missing all selected columns are dropped. |
| `--deduplicate` | CSV: remove duplicate rows. |
| `--output-file` | Write to file instead of stdout. |

**ndjson output:** Each line is one JSON object. JSON files are emitted as-is; HTML/text/markdown files are wrapped in `{"content": "..."}`. If a `manifest.json` is present, a `_url` field is added with the source URL.

**txt output:** Each block starts with `# URL` (when manifest is present), followed by the page content.

**csv output:** Flattens JSON files into tabular rows. For API responses that contain a list (e.g. `organic_results`, `products`, `results`), each list item becomes a row. For single-object responses (e.g. a product page), the object itself is one row. Use `--flatten` to expand nested dicts into dot-notation columns. Use `--columns` to select specific fields and drop incomplete rows. `_url` column is added when `manifest.json` is present.

**manifest.json (batch and crawl):** Both `scrape` batch runs and `crawl` write `manifest.json` to the output directory. Format: `{"<input>": {"file": "N.ext", "fetched_at": "<ISO-8601 UTC>", "http_status": 200, "credits_used": 5, "latency_ms": 1234, "content_sha256": "<sha256>"}}`. Useful for audit trails and monitoring workflows. The `export` command reads both old (plain string values) and new (dict values) manifest formats.

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
