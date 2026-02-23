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

## Examples

Global options (`--output-dir`, `--input-file`, `--concurrency`) go **before** the command:

```bash
scrapingbee --output-dir out --input-file urls.txt scrape
scrapingbee --output-dir out --input-file queries.txt google --country-code us
scrapingbee --output-dir out --input-file asins.txt amazon-product --domain com
scrapingbee --output-dir out --input-file urls.txt --concurrency 10 scrape
```
