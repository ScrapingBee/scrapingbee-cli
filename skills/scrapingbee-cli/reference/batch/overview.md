# Batch mode

Commands with **single input** (URL, query, ASIN, video ID, prompt) support batch via **`--input-file`** and **`--output-dir`**. One output file per input line.

## How it works

- **Input:** File with **one input per line**. Empty lines skipped.
- **Concurrency:** Default = plan limit from usage API. Override with **`--concurrency N`**. CLI caps at plan limit and a safe maximum (~100); warns if you request higher. Lower (e.g. 10) on low-resource machines.
- **Retries:** Global **`--retries`** and **`--backoff`** apply to batch API calls (each item can retry on 5xx or connection errors).
- **Credits:** CLI checks usage API; if credits are below 100 (minimum to run batch), batch **not run**. Run `scrapingbee usage` first. See [reference/usage/overview.md](reference/usage/overview.md).
- **Output folder:** Use **`--output-dir path`** when you need output in a specific directory; otherwise the default is **`batch_<YYYYMMDD_HHMMSS>`**.
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

## Change detection (--diff-dir)

Re-run a batch against a previous run's output directory to detect changes. Files whose content is identical to the previous run are not re-written; the manifest marks them `unchanged: true`.

```bash
# First run
scrapingbee scrape --output-dir run_2025_01_15 --input-file urls.txt

# Second run — compare with previous
scrapingbee --diff-dir run_2025_01_15 --output-dir run_2025_01_16 --input-file urls.txt scrape
```

The `--diff-dir` must point to a folder containing a `manifest.json` from a previous run. Content comparison uses MD5 hashing of the response body. For scheduled monitoring, use `schedule --auto-diff` to inject `--diff-dir` automatically between runs.

## Examples

Global options (`--output-dir`, `--input-file`, `--concurrency`) go **before** the command:

```bash
scrapingbee scrape --output-dir out --input-file urls.txt
scrapingbee google --output-dir out --input-file queries.txt --country-code us
scrapingbee amazon-product --output-dir out --input-file asins.txt --domain com
scrapingbee scrape --output-dir out --input-file urls.txt --concurrency 10
```
