# ScrapingBee CLI

Command-line client for the [ScrapingBee](https://www.scrapingbee.com/) API: scrape URLs (single or batch), crawl sites, check usage and credits, and use Google, Fast Search, Amazon, Walmart, YouTube, and ChatGPT from the terminal.

## Requirements

- **Python 3.10+**

**Setup:** Install (below), then authenticate (Configuration). You need a ScrapingBee API key before any command will work.

## Installation

```bash
pip install scrapingbee-cli
# or (isolated): pipx install scrapingbee-cli
```

From source: clone the repo and run `pip install -e .` in the project root.

## Configuration

You need a ScrapingBee API key:

1. **`scrapingbee auth`** – Validate and save the key to config (use `--api-key KEY` for non-interactive; `--show` to print config path).
2. **Environment** – `export SCRAPINGBEE_API_KEY=your_key`
3. **`.env` file** – In the current directory or `~/.config/scrapingbee-cli/.env`

Remove the stored key with `scrapingbee logout`. Get your API key from the [ScrapingBee dashboard](https://app.scrapingbee.com/).

## Usage

```bash
scrapingbee [command] [arguments] [options]
```

- **`scrapingbee --help`** – List all commands.
- **`scrapingbee [command] --help`** – Options and parameters for that command.

**Options are per-command.** Each command has its own set of options — run `scrapingbee [command] --help` to see them. Common options across batch-capable commands include `--output-file`, `--output-dir`, `--input-file`, `--input-column`, `--concurrency`, `--output-format`, `--retries`, `--backoff`, `--resume`, `--update-csv`, `--no-progress`, `--extract-field`, `--fields`, `--deduplicate`, `--sample`, `--post-process`, `--on-complete`, and `--verbose`. For details, see the [documentation](https://www.scrapingbee.com/documentation/).

### Commands

| Command | Description |
|---------|-------------|
| `usage` | Check credits and max concurrency |
| `auth` / `logout` | Save or remove API key |
| `docs` | Print docs URL; `--open` to open in browser |
| `scrape [url]` | Scrape a URL (HTML, JS, screenshot, extract) |
| `crawl` | Crawl sites following links, with AI extraction and save-pattern filtering |
| `google` / `fast-search` | Search SERP APIs |
| `amazon-product` / `amazon-search` | Amazon product and search |
| `walmart-search` / `walmart-product` | Walmart search and product |
| `youtube-search` / `youtube-metadata` | YouTube search and video metadata |
| `chatgpt` | ChatGPT API |
| `export` | Merge batch/crawl output to ndjson, txt, or csv (with --flatten, --columns) |
| `schedule` | Schedule commands via cron (--name, --list, --stop) |

**Batch mode:** Commands that take a single input support `--input-file` (one line per input, or `.csv` with `--input-column`) and `--output-dir`. Use `--output-format` to choose between `files` (default), `csv`, or `ndjson` streaming. Add `--deduplicate` to remove duplicate URLs, `--sample N` to test on a subset, or `--post-process 'jq .title'` to transform each result. Use `--resume` to skip already-completed items after interruption.

**Parameters and options:** Use space-separated values (e.g. `--render-js false`), not `--option=value`. For full parameter lists, response formats, and credit costs, see **`scrapingbee [command] --help`** and the [ScrapingBee API documentation](https://www.scrapingbee.com/documentation/).

### Key features

- **AI extraction:** `--ai-extract-rules '{"price": "product price", "title": "product name"}'` pulls structured data from any page using natural language — no CSS selectors needed. Works with `scrape`, `crawl`, and batch mode.
- **CSS/XPath extraction:** `--extract-rules '{"title": "h1", "price": ".price"}'` for consistent, cheaper production scraping. Find selectors in browser DevTools.
- **Pipelines:** Chain commands with `--extract-field` — e.g. `google QUERY --extract-field organic_results.url > urls.txt` then `scrape --input-file urls.txt`.
- **Update CSV:** `--update-csv` fetches fresh data and updates the input CSV in-place. Ideal for daily price tracking, inventory monitoring, or any dataset that needs periodic refresh.
- **Crawl with filtering:** `--include-pattern`, `--exclude-pattern` control which links to follow. `--save-pattern` only saves pages matching a regex (others are visited for link discovery but not saved).
- **Output formats:** `--output-format ndjson` streams results as JSON lines; `--output-format csv` writes a single CSV. Default `files` writes individual files.
- **CSV input:** `--input-file products.csv --input-column url` reads URLs from a CSV column.
- **Export:** `scrapingbee export --input-dir batch/ --format csv --flatten --columns "title,price"` merges batch output with nested JSON flattening and column selection.
- **Scheduling:** `scrapingbee schedule --every 1d --name prices scrape --input-file products.csv --update-csv` registers a cron job. Use `--list`, `--stop NAME`, or `--stop all`.
- **Deduplication & sampling:** `--deduplicate` removes duplicate URLs; `--sample 100` processes only 100 random items.
- **RAG chunking:** `scrape --chunk-size 500 --chunk-overlap 50 --return-page-markdown true` outputs NDJSON chunks ready for vector DB ingestion.

### Examples

```bash
scrapingbee usage
scrapingbee scrape "https://example.com" --output-file page.html
scrapingbee scrape "https://example.com/product" --ai-extract-rules '{"title": "product name", "price": "price"}'
scrapingbee google "pizza new york" --extract-field organic_results.url > urls.txt
scrapingbee scrape --input-file urls.txt --output-dir pages --deduplicate
scrapingbee crawl "https://store.com" --output-dir products --save-pattern "/product/" --ai-extract-rules '{"name": "name", "price": "price"}' --max-pages 200 --concurrency 200
scrapingbee export --input-dir products --format csv --flatten --columns "name,price" --output-file products.csv
scrapingbee scrape --input-file products.csv --input-column url --update-csv --ai-extract-rules '{"price": "current price"}'
scrapingbee schedule --every 1d --name price-tracker scrape --input-file products.csv --input-column url --update-csv --ai-extract-rules '{"price": "price"}'
scrapingbee schedule --list
```

## More information

- **[ScrapingBee API documentation](https://www.scrapingbee.com/documentation/)** – Parameters, response formats, credit costs, and best practices.
- **Claude / AI agents:** This repo includes a [Claude Skill](https://github.com/ScrapingBee/scrapingbee-cli/tree/main/skills/scrapingbee-cli) and [Claude Plugin](.claude-plugin/) for agent use with file-based output and security rules.

## Testing

Pytest is configured in `pyproject.toml` (`[tool.pytest.ini_options]`). From the project root:

**1. Install the package with dev dependencies**

```bash
pip install -e ".[dev]"
```

**2. Run tests**

| Command | What runs |
|---------|------------|
| `pytest tests/unit` | Unit tests only (no API key needed) |
| `pytest -m "not integration"` | All except integration (no API key needed) |
| `pytest` | Full suite (integration tests require `SCRAPINGBEE_API_KEY`) |
| `python tests/run_e2e_tests.py` | E2E tests (182 tests, requires `SCRAPINGBEE_API_KEY`) |
| `python tests/run_e2e_tests.py --filter GG` | E2E tests filtered by prefix |

Integration tests call the live ScrapingBee API and are marked with `@pytest.mark.integration`.
