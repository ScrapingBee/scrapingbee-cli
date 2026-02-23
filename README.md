# ScrapingBee CLI

Command-line client for the [ScrapingBee](https://www.scrapingbee.com/) API: scrape URLs (single or batch), crawl sites, check usage and credits, and use Google, Fast Search, Amazon, Walmart, YouTube, and ChatGPT from the terminal.

## Requirements

- **Python 3.10+**

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

**Global flags** (must appear before the subcommand): `--output-file`, `--verbose`, `--output-dir`, `--input-file`, `--concurrency`, `--retries`, `--backoff`. For details, run `scrapingbee --help` or see the [documentation](https://www.scrapingbee.com/documentation/).

### Commands

| Command | Description |
|---------|-------------|
| `usage` | Check credits and max concurrency |
| `auth` / `logout` | Save or remove API key |
| `docs` | Print docs URL; `--open` to open in browser |
| `scrape [url]` | Scrape a URL (HTML, JS, screenshot, extract) |
| `crawl` | Crawl with Scrapy or from URL(s) |
| `google` / `fast-search` | Search SERP APIs |
| `amazon-product` / `amazon-search` | Amazon product and search |
| `walmart-search` / `walmart-product` | Walmart search and product |
| `youtube-search` / `youtube-metadata` | YouTube search and video metadata |
| `chatgpt` | ChatGPT API |

**Batch mode:** Commands that take a single input support `--input-file` (one line per input) and `--output-dir`. Run `scrapingbee usage` before large batches.

**Parameters and options:** Use space-separated values (e.g. `--render-js false`), not `--option=value`. For full parameter lists, response formats, and credit costs, see **`scrapingbee [command] --help`** and the [ScrapingBee API documentation](https://www.scrapingbee.com/documentation/).

### Examples

```bash
scrapingbee usage
scrapingbee docs --open
scrapingbee --output-file page.html scrape "https://example.com"
scrapingbee --output-dir out --input-file urls.txt scrape
scrapingbee --output-file serp.json google "pizza new york"
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
| `pytest` | Full suite (integration tests require `SCRAPINGBEE_API_KEY`) |
| `pytest tests/unit` | Unit tests only (no API key needed) |
| `pytest -m "not integration"` | All except integration (no API key needed) |
| `pytest -v` | Same as above with verbose output (default in config) |

Integration tests call the live ScrapingBee API and are marked with `@pytest.mark.integration`.
