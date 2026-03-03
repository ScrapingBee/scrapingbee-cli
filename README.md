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

1. **`scrapingbee auth`** – Save the key to config (use `--api-key KEY` for non-interactive; `--show` to print config path).
2. **Environment** – `export SCRAPINGBEE_API_KEY=your_key`
3. **`.env` file** – In the current directory or `~/.config/scrapingbee-cli/.env`

Remove the stored key with `scrapingbee logout`. Get your API key from the [ScrapingBee dashboard](https://app.scrapingbee.com/).

## Usage

```bash
scrapingbee [command] [arguments] [options]
```

- **`scrapingbee --help`** – List all commands.
- **`scrapingbee [command] --help`** – Options and parameters for that command.

**Global flags** (can appear before or after the subcommand): `--output-file`, `--verbose`, `--output-dir`, `--input-file`, `--concurrency`, `--retries`, `--backoff`, `--resume`, `--diff-dir`, `--no-progress`, `--extract-field`, `--fields`. For details, run `scrapingbee --help` or see the [documentation](https://www.scrapingbee.com/documentation/).

### Commands

| Command | Description |
|---------|-------------|
| `usage` | Check credits and max concurrency |
| `auth` / `logout` | Save or remove API key |
| `docs` | Print docs URL; `--open` to open in browser |
| `scrape [url]` | Scrape a URL (HTML, JS, screenshot, extract) |
| `crawl` | Crawl with Scrapy or from URL(s)/sitemap |
| `google` / `fast-search` | Search SERP APIs |
| `amazon-product` / `amazon-search` | Amazon product and search |
| `walmart-search` / `walmart-product` | Walmart search and product |
| `youtube-search` / `youtube-metadata` | YouTube search and video metadata |
| `chatgpt` | ChatGPT API |
| `export` | Merge batch/crawl output to ndjson, txt, or csv |
| `schedule` | Run any command on a repeating interval |

**Batch mode:** Commands that take a single input support `--input-file` (one line per input) and `--output-dir`. Run `scrapingbee usage` before large batches. Use `--resume` to skip already-completed items after interruption.

**Parameters and options:** Use space-separated values (e.g. `--render-js false`), not `--option=value`. For full parameter lists, response formats, and credit costs, see **`scrapingbee [command] --help`** and the [ScrapingBee API documentation](https://www.scrapingbee.com/documentation/).

### Key features

- **Pipelines:** Chain commands with `--extract-field` — e.g. `google QUERY --extract-field organic_results.url > urls.txt` then `scrape --input-file urls.txt`.
- **Change detection:** `--diff-dir old_run/` skips files unchanged since the previous run (by MD5). Manifest marks unchanged items.
- **Scheduling:** `scrapingbee schedule --every 1h google "python news"` runs hourly. Add `--auto-diff` for automatic change detection between runs.
- **RAG chunking:** `scrape --chunk-size 500 --chunk-overlap 50 --return-page-markdown true` outputs NDJSON chunks ready for vector DB ingestion.
- **Export:** `scrapingbee export --input-dir batch/ --format csv` merges batch output into a single CSV, ndjson, or txt file.

### Examples

```bash
scrapingbee usage
scrapingbee docs --open
scrapingbee scrape "https://example.com" --output-file page.html
scrapingbee scrape --output-dir out --input-file urls.txt
scrapingbee google "pizza new york" --output-file serp.json
scrapingbee google "python tutorials" --extract-field organic_results.url > urls.txt
scrapingbee export --input-dir batch_output/ --format csv > results.csv
scrapingbee schedule --every 30m --auto-diff --output-dir runs/ google "breaking news"
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
| `pytest tests/unit` | Unit tests only (343 tests, no API key needed) |
| `pytest -m "not integration"` | All except integration (no API key needed) |
| `pytest` | Full suite (integration tests require `SCRAPINGBEE_API_KEY`) |
| `python tests/run_e2e_tests.py` | E2E tests (182 tests, requires `SCRAPINGBEE_API_KEY`) |
| `python tests/run_e2e_tests.py --filter GG` | E2E tests filtered by prefix |

Integration tests call the live ScrapingBee API and are marked with `@pytest.mark.integration`.
