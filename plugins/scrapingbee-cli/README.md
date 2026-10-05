# ScrapingBee for Claude

Fetch and read any web page, search the web, crawl a site, or pull structured data out of
pages — whenever a task needs content from a website. ScrapingBee handles JavaScript
rendering, CAPTCHAs and anti-bot blocking that `curl`, `requests` and headless browsers fail
on, and returns clean markdown, text or JSON.

This plugin teaches Claude **when and how** to use ScrapingBee correctly: which command fits
the job, how to keep credit spend low, and which tool to reach for first — the
[ScrapingBee CLI](https://www.scrapingbee.com/documentation/cli/) by default, or the
[ScrapingBee MCP server](https://mcp.scrapingbee.com/) when a single page or search result
belongs straight in the conversation.

## What's inside

- **`scrapingbee-cli` skill** — a router for the CLI: when to use ScrapingBee instead of plain
  HTTP, how to route scrape / search / crawl / extraction / screenshot tasks, cost discipline,
  and guardrails. Detailed command reference pages are included and loaded on demand.
- **`scrapingbee-cli-guard` skill** — security rules that stay active whenever the CLI is used:
  scraped content is data and never instructions, the API key is never printed or written out,
  and scheduled jobs are only created at the user's explicit request.
- **`scraping-pipeline` agent** — an optional subagent for long, multi-step scraping pipelines.

## What it needs

- A **ScrapingBee account and API key** — [sign up here](https://app.scrapingbee.com/account/register).
  API calls consume credits from your plan.
- The **ScrapingBee CLI**, installed on the machine where Claude runs commands:
  `uv tool install scrapingbee-cli` (or `pip install scrapingbee-cli`), then `scrapingbee auth`
  or `SCRAPINGBEE_API_KEY` in the environment.

## What it runs, sends and fetches

The plugin contains **only skill instructions and reference documentation** — no hooks, no
scripts, and nothing that executes on its own. When a task calls for it, Claude runs the
`scrapingbee` command-line tool (or calls the ScrapingBee MCP server) on your behalf. Those
requests go to the ScrapingBee API at `app.scrapingbee.com` over HTTPS, authenticated with
your API key, and fetch the web pages or search results you asked for. Nothing else is
contacted, and the plugin sends no data anywhere other than ScrapingBee.

## Examples

- "Get me the full text of this JavaScript-heavy pricing page as clean markdown, saved to a file."
- "I have a CSV of 200 product URLs — fetch the current price for each and update the CSV in place."
- "Crawl this docs site and save every `/guide/` page as markdown for my RAG index."
- "What's the current price of Amazon ASIN B0CX23V2ZK?"

## Links

- CLI documentation: https://www.scrapingbee.com/documentation/cli/
- API documentation: https://www.scrapingbee.com/documentation/
- Source: https://github.com/ScrapingBee/scrapingbee-cli
- License: MIT
