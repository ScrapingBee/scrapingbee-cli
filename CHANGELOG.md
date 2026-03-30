# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.1] - 2026-03-30

### Added

- **`--scraping-config` parameter** for `scrape` and `crawl` commands. Apply a pre-saved scraping configuration by name from the ScrapingBee dashboard. Inline options override config settings.
- **Parameter value flexibility.** Choice parameters now accept both hyphens and underscores interchangeably (e.g. `--sort-by price-low` and `--sort-by price_low` both work).
- **Improved command whitelist validation.**
- **Improved security rules in skill files.**

## [1.3.0] - 2026-03-27

### Added

- **Security hardening for shell execution features.** `--post-process`, `--on-complete`, and `schedule` are now disabled by default and require explicit human setup to enable. See CLI documentation for setup instructions.
- **`scrapingbee unsafe` command** for managing advanced feature status.
- **Audit logging.**
- **Guard skill** for AI agent environments.
- **Security rules in skill files.**

### Changed

- **`--post-process`, `--on-complete`, and `schedule`** help text now indicates these require advanced setup.
- **`scrapingbee logout`** resets all advanced feature settings.

## [1.2.3] - 2026-03-25

### Added

- **ChatGPT `--search`, `--add-html`, `--country-code` flags:** The `chatgpt` command now supports web-enhanced responses (`--search true`), full HTML inclusion (`--add-html true`), and geolocation (`--country-code gb`). `--search false` is silently ignored (only `true` sends the param).
- **Auto-prepend `https://`:** URLs without a scheme (e.g. `example.com`) now automatically get `https://` prepended, matching curl/httpie behavior. Works for `scrape`, `crawl`, and `--from-sitemap`.
- **`--extract-field` path suggestions:** When `--extract-field` doesn't match any data, the CLI now prints a warning with all available dot-paths instead of silent empty output.
- **Exact credit costs in `--verbose`:** SERP commands (Google, Fast Search, Amazon, Walmart, YouTube, ChatGPT) now show exact credit costs based on request parameters (e.g. `Credit Cost: 10` for Google light requests) instead of estimated ranges.
- **Unit tests for all v1.2.3 changes:** 39 new unit tests in `tests/unit/test_v122_fixes.py` plus 8 new e2e tests (FX-01 through FX-08).
- **CLI documentation page:** Full docs at https://www.scrapingbee.com/documentation/cli/ — installation, authentication, all commands, parameters, pipelines, and examples.

### Fixed

- **`--allowed-domains` crawl bug:** Fixed a bug where `--allowed-domains` caused crawls to produce no output. Scrapy's built-in `OffsiteMiddleware` was reading the spider's `allowed_domains` attribute and filtering out all ScrapingBee proxy requests. Renamed to `_cli_allowed_domains` to avoid the conflict.
- **`--max-depth` with non-HTML modes:** Disabled Scrapy's built-in `DepthMiddleware` which incorrectly incremented depth on discovery re-fetches, breaking `--max-depth` when using `--ai-query`, `--return-page-markdown`, or other non-HTML output modes.
- **Misleading screenshot warning removed:** `--screenshot-full-page true` without `--screenshot` no longer prints a false "has no effect" warning — the API handles it correctly and produces a valid screenshot.
- **Fast Search credit cost:** Corrected from 5 to 10 credits in the estimated fallback.

### Changed

- **Installation recommendation:** Docs now recommend `uv tool install scrapingbee-cli` over `pip install` for isolated, globally-available installation without virtual environment management.
- **Version bumped to 1.2.3** across `pyproject.toml`, `__init__.py`, all skill files, and plugin manifests.

## [1.2.2] - 2026-03-16

### Changed

- **Plugin directory restructured:** Separated marketplace catalog from plugin content. Plugin now lives at `plugins/scrapingbee-cli/` with its own `.claude-plugin/plugin.json`, matching the Claude Code marketplace spec.
- **`marketplace.json` fixed:** Moved top-level `description` to `metadata.description`, updated plugin `source` to `./plugins/scrapingbee-cli`, removed non-spec `$schema` field.
- **`AGENTS.md` upgraded:** Now comprehensive and self-contained — covers all commands, options, pipelines, extraction, crawling, scheduling, credit costs, troubleshooting, and known limitations. Serves as the single source of truth for tools that read `AGENTS.md` (Codex CLI, Cursor, Windsurf, Amp, RooCode, Continue, and others).

### Added

- **GitHub Copilot skills:** Added `.github/skills/scrapingbee-cli/` for Copilot skill discovery.
- **OpenCode skills:** Added `.opencode/skills/scrapingbee-cli/` for OpenCode skill discovery.
- **`sync-skills.sh` updated:** Now syncs skills to `.github/skills/` and `.opencode/skills/` in addition to existing destinations.

## [1.2.1] - 2026-03-16

### Fixed

- **Marketplace plugin install:** Changed `"source": "."` to `"source": "./"` in `.claude-plugin/marketplace.json` to match Claude Code's marketplace schema validator.

## [1.2.0] - 2026-03-16

### Added

- **`--update-csv`:** Fetch fresh data and update the input CSV file in-place with the latest results. Replaces the old `--diff-dir` workflow.
- **Cron-based `schedule`:** `schedule --every INTERVAL --name NAME CMD` registers a cron job. Multiple named schedules supported. Use `--list` to view active schedules with running time, `--stop NAME` or `--stop all` to remove them. Replacing a schedule prompts for confirmation.
- **Per-command options:** Options are now per-command (shown via `scrapingbee [command] --help`) instead of global. API-specific options are grouped (Search, Filters, Locale, etc.).
- **`--output-format [files|csv|ndjson]`:** Choose batch output format — `files` (default, individual files), `csv` (single CSV), or `ndjson` (streaming JSON lines to stdout).
- **`--deduplicate`:** Normalize URLs and remove duplicates before batch processing. Also available on `export` for removing duplicate CSV rows.
- **`--sample N`:** Process only N random items from input file — useful for testing configurations cheaply.
- **`--input-column`:** CSV input support — `--input-file data.csv --input-column url` reads from a named or indexed column.
- **`--post-process`:** Pipe each batch result through a shell command (e.g. `--post-process 'jq .title'`) before saving.
- **Crawl `--include-pattern` / `--exclude-pattern`:** Regex filters for which links the crawler follows.
- **Crawl `--save-pattern`:** Only save pages matching this regex. Other pages are visited for link discovery but not saved. Useful for crawling through category pages to reach detail pages.
- **Rich batch progress:** Progress display now shows `[N/total] 50 req/s | ETA 2m 30s | Failures: 3%`.
- **Export `--flatten`:** Recursively flatten nested JSON dicts to dot-notation CSV columns. Lists of dicts are index-expanded (e.g. `buybox.0.price`).
- **Export `--columns`:** Cherry-pick CSV columns by name. Rows missing all selected columns are dropped.
- **Auth validates API key:** `scrapingbee auth` now calls the usage endpoint to verify the key before saving.
- **Logout checks schedules:** `scrapingbee logout` warns about active schedules and offers to stop them.
- **Active schedule hint:** Every command shows a one-line reminder when schedules are running.
- **Crawl resilience:** `parse()` catches errors from non-HTML responses (JSON, plain text) instead of crashing.

### Removed

- **`--diff-dir`:** Removed from batch and export. Use `--update-csv` for refreshing data instead.
- **`--auto-diff`:** Removed completely.
- **`--daemon`:** Removed from schedule. Schedule now uses cron jobs that persist across sessions.
- **Global flags:** Options are now per-command. Removed option reorder logic and `--option=value` rejection.

### Fixed

- **Crawl broken on Scrapy 2.14:** Fixed `start` → `start_requests` rename that broke the spider.
- **Crawl `--max-pages`:** Now enforced at both spider and Scrapy downloader level (`CLOSESPIDER_PAGECOUNT`). Counts actual fetched pages, not discovered URLs.
- **Crawl JSON response crash:** `_extract_hrefs_from_response` now catches `ValueError` when response is JSON instead of HTML.
- **`--robots.txt`:** Disabled `ROBOTSTXT_OBEY` since ScrapingBee handles robots.txt compliance.
- **"Batch complete" sent to stderr:** Moved back to stdout.
- **CSV export for product pages:** `_find_main_list` heuristic improved to not expand reviews/variants from single-item detail pages.
- **Integration test fixes:** Fixed hyphenated choice values (`best-match`, `this-week`), changed Amazon `--country us` to `gb`.

## [1.1.0] - 2025-03-02

### Added

- **Shell-safe YouTube duration aliases:** `--duration short` / `medium` / `long` as aliases for `"<4"` / `"4-20"` / `">20"`. Raw values still work (backward compatible).
- **Position-independent global options:** `--verbose`, `--output-file`, and all other global flags now work when placed after the subcommand (e.g. `scrapingbee google --verbose "query"`), in addition to before it.
- **Shell-safe `--extract-field` dot syntax:** `--extract-field organic_results.url` replaces the old bracket syntax (`organic_results[].url`). No shell quoting needed.

- **`AGENTS.md`:** Added project-root context file for tools that have no plugin/skill system. Read automatically by Amp, RooCode, Windsurf, Kilo Code, and OpenAI Codex CLI (the only mechanism Codex supports). Contains install, auth, all commands, global flags, pipeline recipes, credit costs, and troubleshooting — self-contained so no SKILL.md is needed.
- **Multi-tool agent compatibility:** `scraping-pipeline` agent is now placed in all major AI coding tool directories — `.gemini/agents/` (Gemini CLI), `.github/agents/` (GitHub Copilot), `.augment/agents/` (Augment Code), `.factory/droids/` (Factory AI), `.kiro/agents/` (Kiro IDE), `.opencode/agents/` (OpenCode). All use the same markdown+YAML content as `.claude/agents/` (already covers Claude Code, Cursor, Amp, RooCode, Windsurf, Augment Code). Amazon Q gets `.amazonq/cli-agents/scraping-pipeline.json` (JSON format required by that tool).
- **Multi-tool skill compatibility:** `SKILL.md` is mirrored to `.agents/skills/scrapingbee-cli/` (Amp + RooCode + OpenCode — none read `AGENTS.md` for skills) and `.kiro/skills/scrapingbee-cli/` (Kiro — uses `.kiro/steering/` for context, not `AGENTS.md`). Windsurf and Kilo Code are covered by `AGENTS.md` instead (both read it natively), so no dedicated skill directories are needed for them.
- **`.claude-plugin/marketplace.json`:** Added Claude Code plugin marketplace manifest so the `scrapingbee-cli` GitHub repo is recognized as a self-contained plugin marketplace. Enables users to install via Claude Code's plugin system (`/plugins install scrapingbee@scrapingbee`) after registering the marketplace. Declares the single `scrapingbee-cli` plugin with `source: "."` pointing to the repo root where `skills/` is discovered automatically.

- **`--extract-field` global flag:** Extract values from a JSON response using a path expression and output one value per line — e.g. `--extract-field organic_results.url` extracts each URL from a SERP, ready to pipe into `--input-file`. Supports array expansion (`key.subkey`) and top-level scalars/lists (`key`). Takes precedence over `--fields`.
- **`--fields` global flag:** Filter JSON response output to specified comma-separated top-level keys — e.g. `--fields title,price,rating`. Works on single-object and list responses.
- **Per-request metadata in batch manifest:** `write_batch_output_to_dir` now writes `manifest.json` (alongside the numbered output files) with per-item metadata: `{"input": {"file": "N.ext", "fetched_at": "<ISO-8601>", "http_status": 200}}`. Enables time-series analysis for price monitoring, change detection, and audit trails.
- **Enriched crawl manifest:** `crawl` manifest.json now uses the same enriched per-item format: `{"url": {"file": "N.ext", "fetched_at": "<ISO-8601>", "http_status": 200}}`.
- **`export --diff-dir`:** Compare a new batch/crawl directory with a previous one and output only items whose content has changed or are new. Unchanged items (same file content by MD5) are skipped. Prints a count of skipped items to stderr.
- **`google --search-type ai_mode`:** Added the `ai_mode` search type to the `--search-type` choice list (returns an AI-generated answer).
- **`youtube-metadata` accepts full URLs:** The command now auto-extracts the video ID from full YouTube URLs (`youtube.com/watch?v=...`, `youtu.be/...`, `/shorts/...`), enabling direct piping from `youtube-search --extract-field results.link` without `sed`.
- **Claude Skill — Pipelines section:** `SKILL.md` now has a prominent Pipelines table at the top listing the 6 main multi-step patterns with exact one-liner commands.
- **Claude Skill — Pipeline subagent:** `.claude/agents/scraping-pipeline.md` defines an isolated subagent that orchestrates full scraping pipelines (credit check → search → batch → export) without polluting the main conversation context.
- **Claude Skill — `--extract-field` examples added to all search command docs:** `fast-search`, `amazon-search`, `walmart-search`, `youtube-search`, and `google` docs now include a "Pipeline" section showing how to chain into the downstream batch command.
- **Claude Skill — Change monitoring pattern:** `patterns.md` documents the `--diff-dir` monitoring workflow and notes that `manifest.json` now includes `fetched_at` / `http_status` per item for time-series analysis.
- **`youtube-search` response normalization:** The command now parses the raw YouTube API payload and outputs a clean JSON structure — `results` is a proper array (not a JSON-encoded string) with flat fields: `link` (full `https://www.youtube.com/watch?v=…` URL), `video_id`, `title`, `channel`, `views`, `published`, `duration`. Enables `--extract-field results.link` to work directly for piping into `youtube-metadata`.
- **`walmart-search` → `walmart-product` pipeline:** Search results include a top-level `id` field per product (e.g. `"921722537"`), enabling `--extract-field products.id walmart-search QUERY | walmart-product` — an exact parallel to the Amazon search → product pipeline. Docs updated to document this pipeline.
- **Claude Skill — `walmart-search → walmart-product` pipeline:** `walmart/search.md`, `patterns.md`, and `SKILL.md` pipeline table updated to document `--extract-field products.id` → `walmart-product`.
- **Claude Skill — YouTube search output schema corrected:** `reference/youtube/search-output.md` now documents the clean normalized schema (link, video_id, title, channel, views, published, duration).
- **Tests:** Unit tests for `_normalize_youtube_search` (8 tests: results array, link construction, title/channel extraction, video_id field, items without videoId skipped, already-array passthrough, invalid JSON passthrough, other fields preserved).
- **Tests:** Unit tests for `write_batch_output_to_dir` manifest writing (5 tests: correct structure, errors omitted, skipped items omitted, no manifest when all fail, screenshot subdir in manifest path).
- **Tests:** Unit tests for `_extract_field_values` (7 tests: array subkey, top-level scalar/list, missing key, invalid JSON, missing subkey items, empty array) and `_filter_fields` (5 tests: dict filter, nonexistent keys, empty fields, invalid JSON, list filter). Global `--extract-field`, `--fields`, and `ai_mode` coverage in CLI help tests.
- **Tests:** Unit tests for `export --diff-dir` (4 tests: all unchanged, changed item, new item, mixed). Unit test for new dict-valued manifest format in CSV export.

- **`schedule` command:** `scrapingbee schedule --every INTERVAL CMD` repeatedly runs any scrapingbee command at a fixed interval (supports `30s`, `5m`, `1h`, `2d`). `--auto-diff` automatically injects `--diff-dir` from the previous run for change detection across runs.
- **`--diff-dir` global option:** Compare batch/crawl output with a previous run — unchanged files (by MD5) are not re-written and are marked `"unchanged": true` in manifest.json. Works with all batch commands.
- **RAG-ready chunked output:** `scrape --chunk-size N [--chunk-overlap M]` splits text/markdown responses into overlapping NDJSON chunks (each line: `{"url", "chunk_index", "total_chunks", "content", "fetched_at"}`). Ready for vector DB ingestion or LLM context windows.
- **Enriched batch manifest:** `manifest.json` now includes `credits_used` (from `Spb-Cost` header), `latency_ms` (request timing), and `content_md5` (MD5 hash of response body) per item. `content_md5` powers the `--diff-dir` change detection.
- **Estimated credit costs in verbose mode:** SERP endpoints (Google, Fast Search, Amazon, Walmart, YouTube, ChatGPT) don't return the `Spb-Cost` header. `--verbose` now shows estimated credit cost from hardcoded values in `credits.py` when the header is absent.
- **E2E test suite:** 182 end-to-end tests covering all commands, batch/crawl, export, schedule, diff-dir, verbose output, and edge cases.
- **Tests:** Unit tests for `read_input_file`, crawl spider manifest fields (`credits_used`, `latency_ms`), estimated credit cost display, `chunk_text`, `_parse_duration`, schedule helpers.

- **Progress counter:** Batch runs now print a per-item `[n/total]` counter to stderr as each item completes (with `(error)` or `(skipped)` suffix when applicable). Suppress with global `--no-progress` flag.
- **CSV export:** `scrapingbee export --format csv` flattens JSON batch/crawl output to a tabular CSV. API responses with a top-level list (e.g. `organic_results`, `products`, `results`) expand to one row per item; single-object responses (e.g. product pages) produce one row per file. Nested dicts/arrays are serialised as JSON strings. `_url` column is added when `manifest.json` is present.
- **Chained workflow docs:** `reference/usage/patterns.md` now includes end-to-end pipeline recipes: SERP → scrape result pages, Amazon search → product details (with CSV export), YouTube search → video metadata, and batch SERP for many queries.
- **Resume (batch):** `--resume` global flag skips already-completed items when re-running a batch command against an existing `--output-dir`. Completed items are detected by scanning for `N.<ext>` files (`.err` files are not treated as complete). Applies to all batch commands: `scrape`, `google`, `fast-search`, `amazon-product`, `amazon-search`, `walmart-product`, `walmart-search`, `youtube-metadata`, `youtube-search`, `chatgpt`.
- **Resume (crawl):** `--resume` also resumes an interrupted crawl: existing `manifest.json` is loaded to pre-populate already-visited URLs, preventing re-fetching.
- **Crawl manifest:** `crawl` now writes `manifest.json` (URL → relative filename map) to the output directory when the crawl finishes, enabling resume and export.
- **Sitemap ingestion:** `crawl --from-sitemap <url>` fetches a sitemap (or sitemap index) and crawls all discovered URLs. Handles `<sitemapindex>` recursively (depth limit 2) and both namespaced and bare XML.
- **Export command:** `scrapingbee export --input-dir <dir> [--format ndjson|txt]` merges numbered batch/crawl output files into a single stream. NDJSON mode enriches each record with `_url` when a `manifest.json` is present; TXT mode emits `# URL` headers followed by page text. Output respects `--output-file`.
- **CI:** GitHub Actions workflow (`.github/workflows/ci.yml`) runs unit tests across Python 3.10–3.13 on every push and pull request.
- **Tests:** Unit tests for `validate_batch_run` (credit guard, concurrency guard).
- **Tests:** Unit tests for `_find_main_list`, `_flatten_value`, and `export --format csv` (17 tests covering flat objects, list expansion, non-JSON skipping, manifest URL injection, and empty-input error).
- **Tests:** Unit tests for `_find_completed_n` (nonexistent dir, numbered files, ignores `.err`, ignores non-numeric stems, finds files in subdirectories).
- **Tests:** Unit tests for `run_batch_async` skip-n (resume) behaviour: skipped items are marked `skipped=True` with empty body; empty `skip_n` processes all items.
- **Tests:** Unit tests for the crawl double-fetch discovery mechanism (`parse()` triggers discovery when no links; `_parse_discovery_links_only()` follows links without saving).
- **Tests:** Help-output tests for every command (youtube-search, youtube-metadata, walmart-search, walmart-product, amazon-product, amazon-search, fast-search, chatgpt, crawl, export, schedule, usage, scrape, google) — verifying key params appear in `--help`. YouTube choice constants tests. Global option reordering tests (15 edge cases). Total: 343 unit tests.
- **Claude Skill:** `reference/usage/patterns.md` — multi-step workflow recipes: crawl + AI extraction (Option A one-command; Option B crawl-then-batch), batch SERP pipeline.
- **Claude Skill:** Prerequisites section at the top of `SKILL.md` so AI agents install the CLI and authenticate before issuing commands.
- **Claude Skill:** Output schemas (truncated JSON examples) added to all API reference docs: `google`, `fast-search`, `amazon-product`, `amazon-search`, `walmart-product`, `walmart-search`, `youtube-search`, `youtube-metadata`, `chatgpt`.
- **Claude Skill:** `reference/troubleshooting.md` — decision tree covering empty responses, 403/429 errors, `.err` files, crawl stopping early, `--ai-query` returning null, missing output files, and proxy recommendations.
- **Claude Skill:** `reference/batch/export.md` — documents the `export` command and `--resume` flag with examples.
- **Claude Skill:** `reference/scrape/extraction.md` — documents `--ai-query` and `--ai-extract-rules` response formats with JSON examples.
- **Claude Skill:** `reference/scrape/strategies.md` — "Why use ScrapingBee instead of WebFetch or curl?" section explaining automatic proxy rotation, CAPTCHA handling, and JS rendering as reasons to prefer ScrapingBee for all web scraping tasks.
- **Claude Skill:** `reference/crawl/overview.md` — documents sitemap mode (`--from-sitemap`), resume (`--resume`), `manifest.json`, and the three crawl modes (Scrapy project, URL-based, sitemap-based).

### Fixed

- **Claude Skill:** `SKILL.md` frontmatter `version` corrected from `1.3.0` to `1.1.0` to match `pyproject.toml`.
- **Claude Skill:** `reference/crawl/overview.md` now accurately documents the double-fetch discovery mechanism: `--return-page-text` (and other non-HTML options) triggers a second plain-HTML fetch for link discovery, costing 2 credits per affected page. `--return-page-markdown` is exempt because markdown links are extracted directly.
- **Claude Skill:** Removed spurious `add_html` / `full_html` reference from `reference/chatgpt/overview.md` (the ChatGPT command has no `--add-html` option).
- **Claude Skill:** `reference/usage/patterns.md` Option B uses `--preset extract-links` for concrete URL discovery and documents that crawl output files are numbered (no URL manifest).
- **Tests:** `test_root_version` now asserts the exact `__version__` string instead of the fragile `"1.0" in out` substring check.

## [1.0.1] - Fixed SKILL.md

### Fixed

- **Claude Skill:** Removed invalid `tags` key from `SKILL.md` frontmatter so it validates against allowed properties (`name`, `description`, `version`, etc.).

## [1.0.0] - Initial release

### Added

- CLI for ScrapingBee API: `scrapingbee` with subcommands for scrape, batch, crawl, usage, auth, and specialized tools (Google, Fast Search, Amazon, Walmart, YouTube, ChatGPT).
- Space-separated option syntax (`--option value`); `--option=value` is rejected.
- Claude Skill documentation under `skills/scrapingbee-cli/` for AI-assisted usage.
