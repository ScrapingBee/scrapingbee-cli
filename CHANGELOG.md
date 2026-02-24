# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.1] - Fixed SKILL.md

### Fixed

- **Claude Skill:** Removed invalid `tags` key from `SKILL.md` frontmatter so it validates against allowed properties (`name`, `description`, `version`, etc.).

## [1.0.0] - Initial release

### Added

- CLI for ScrapingBee API: `scrapingbee` with subcommands for scrape, batch, crawl, usage, auth, and specialized tools (Google, Fast Search, Amazon, Walmart, YouTube, ChatGPT).
- Space-separated option syntax (`--option value`); `--option=value` is rejected.
- Claude Skill documentation under `skills/scrapingbee-cli/` for AI-assisted usage.
