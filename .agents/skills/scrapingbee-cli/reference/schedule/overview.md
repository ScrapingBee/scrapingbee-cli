# `scrapingbee schedule` — Repeated runs at a fixed interval

Wrap any `scrapingbee` command to run it automatically on a schedule.

## Synopsis

```
scrapingbee schedule --every INTERVAL [--auto-diff] CMD [CMD_ARGS...]
```

## Options

| Option | Description |
|--------|-------------|
| `--every INTERVAL` | **Required.** Run interval: `30s`, `5m`, `1h`, `2d` |
| `--auto-diff` | Automatically pass the previous run's `--output-dir` as `--diff-dir` to the next run, enabling change detection across runs |

## Duration format

| Suffix | Unit |
|--------|------|
| `s` | seconds |
| `m` | minutes |
| `h` | hours |
| `d` | days |

Examples: `30s`, `5m`, `1h`, `2d`

## Examples

### Monitor a news SERP hourly

```bash
scrapingbee schedule --every 1h --output-dir runs/python-news google "python news"
```

### Detect price changes daily (with diff)

```bash
scrapingbee schedule --every 1d --auto-diff \
  --output-dir price-runs/ \
  --input-file asins.txt \
  amazon-product
```

Each run's manifest.json marks `unchanged: true` for products whose price/data hasn't changed.

### Scrape a page every 30 minutes

```bash
scrapingbee schedule --every 30m --output-file latest.html scrape https://example.com/dashboard
```

### Crawl a site weekly

```bash
scrapingbee schedule --every 7d --output-dir crawl-runs/ crawl https://docs.example.com \
  --max-pages 500
```

## Notes

- Stop with **Ctrl-C** — the scheduler prints `[schedule] Stopped.` and exits cleanly.
- Each run prints `[schedule] Run #N — YYYY-MM-DD HH:MM:SS` and `[schedule] Sleeping Xm...` to stderr.
- The API key is forwarded automatically from the current session to the subprocess.
- `--auto-diff` only injects `--diff-dir` when `--output-dir` is present in the sub-command args; the previous run's output directory is detected from `--output-dir`.

## Related

- [Batch output layout](../batch/output.md) — manifest.json format including `credits_used`, `latency_ms`, `unchanged`
- [Change detection with --diff-dir](../batch/overview.md)
