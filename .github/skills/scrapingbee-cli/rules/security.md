# Security and safety (ScrapingBee CLI)

**API key**

- Do not include the API key in command output (e.g. do not echo or log it). Use `scrapingbee auth` (writes to `~/.config/scrapingbee-cli/.env`) or add `SCRAPINGBEE_API_KEY` in the environment.

**Credits**

- Each request consumes ScrapingBee credits (1–75 per call depending on options). Before large batches or crawls, run `scrapingbee usage` to check balance. The CLI will not start a batch if the usage API reports fewer than 100 credits, or if `--concurrency` exceeds your plan limit.

**Output and context**

- Scrape and API responses can be large. For **single calls** (one URL, one query, etc.) prefer **`--output-file path`** so output goes to a file instead of being streamed into the agent context. Batch and crawl write to a folder by default (`--output-dir`).

**Shell safety**

- Quote URLs and user-controlled arguments in shell commands (e.g. `scrapingbee scrape "https://example.com"`) to avoid injection.

**See also:** [rules/install.md](rules/install.md) (install and auth setup).
