# Batch mode

> **Syntax:** use space-separated values — `--option value`, not `--option=value`.

Commands with **single input** (URL, query, ASIN, video ID, prompt) support batch via **`--input-file`** and **`--output-dir`**. One output file per input line.

## How it works

- **Input:** File with **one input per line**. Empty lines skipped. Use `--input-file -` to read from stdin. CSV files auto-detected: use `--input-column url` to specify the column (name or 0-based index).
- **Concurrency:** Default = plan limit from usage API. Override with **`--concurrency N`**. CLI caps at plan limit and a safe maximum (~100).
- **Retries:** Global **`--retries`** and **`--backoff`** apply to batch API calls.
- **Credits:** CLI checks usage API; if credits are below 100, batch **not run**. Run `scrapingbee usage` first.
- **Output format:** **`--output-format files`** (default) writes individual files. **`--output-format csv`** writes a single CSV. **`--output-format ndjson`** streams JSON lines to stdout.
- **Output folder:** Use **`--output-dir path`** for a specific directory; default is **`batch_<YYYYMMDD_HHMMSS>`**.
- **Deduplication:** **`--deduplicate`** normalizes URLs (lowercase domain, strip fragment/trailing slash) and removes duplicates before processing.
- **Sampling:** **`--sample N`** processes only N random items from input — useful for testing configurations.
- **Post-processing:** **`--post-process 'jq .title'`** pipes each result body through a shell command before saving.
- **Constraint:** Cannot use `--input-file` with a positional argument.

## Input type per command

| Command | Input per line | Reference |
|---------|----------------|-----------|
| scrape | URL | [reference/scrape/overview.md](reference/scrape/overview.md) |
| google | Search query | [reference/google/overview.md](reference/google/overview.md) |
| fast-search | Search query | [reference/fast-search/overview.md](reference/fast-search/overview.md) |
| amazon-product | ASIN | [reference/amazon/product.md](reference/amazon/product.md) |
| amazon-search | Search query | [reference/amazon/search.md](reference/amazon/search.md) |
| walmart-search | Search query | [reference/walmart/search.md](reference/walmart/search.md) |
| walmart-product | Product ID | [reference/walmart/product.md](reference/walmart/product.md) |
| youtube-search | Search query | [reference/youtube/search.md](reference/youtube/search.md) |
| youtube-metadata | Video ID | [reference/youtube/metadata.md](reference/youtube/metadata.md) |
| chatgpt | Prompt | [reference/chatgpt/overview.md](reference/chatgpt/overview.md) |

Output layout: [reference/batch/output.md](reference/batch/output.md).

## Update CSV (--update-csv)

Re-fetch data for every row in the input CSV and update the file in-place with the latest results. Useful for refreshing price lists, product catalogs, or any dataset that needs periodic updates.

```bash
# Fetch fresh data and update the CSV in-place
scrapingbee scrape --input-file products.csv --input-column url --update-csv

# Combine with scheduling for automatic refreshes
scrapingbee schedule --every 1d --name prices scrape --input-file products.csv --input-column url --update-csv
```

## Completion hook (--on-complete)

Run a shell command after the batch finishes. The command has access to these environment variables:

| Variable | Description |
|----------|-------------|
| `SCRAPINGBEE_OUTPUT_DIR` | Absolute path to the output directory. |
| `SCRAPINGBEE_SUCCEEDED` | Number of successful requests. |
| `SCRAPINGBEE_FAILED` | Number of failed requests. |

```bash
scrapingbee scrape --output-dir out --input-file urls.txt --on-complete "echo Done: \$SCRAPINGBEE_SUCCEEDED succeeded, \$SCRAPINGBEE_FAILED failed"
```

## Examples

```bash
scrapingbee scrape --output-dir out --input-file urls.txt
scrapingbee google --output-dir out --input-file queries.txt --country-code us
scrapingbee amazon-product --output-dir out --input-file asins.txt --domain com
scrapingbee scrape --output-dir out --input-file urls.txt --concurrency 10
```
