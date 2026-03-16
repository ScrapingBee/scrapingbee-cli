# `scrapingbee schedule` — Cron-based recurring runs

> **Syntax:** use space-separated values — `--option value`, not `--option=value`.

Register any `scrapingbee` command as a cron job that runs automatically on a repeating interval.

## Synopsis

```
scrapingbee schedule --every INTERVAL [--name NAME] CMD [CMD_ARGS...]
scrapingbee schedule --list
scrapingbee schedule --stop NAME
scrapingbee schedule --stop all
```

## Options

| Option | Description |
|--------|-------------|
| `--every INTERVAL` | **Required** (unless `--list` or `--stop`). Run interval: `5m`, `30m`, `1h`, `2d` |
| `--name NAME` | Name the schedule for easy identification and management |
| `--stop NAME` | Remove a named cron entry. Use `--stop all` to remove all scrapingbee schedules |
| `--list` | Show all active scrapingbee schedules with their running time |

## Duration format

| Suffix | Unit |
|--------|------|
| `m` | minutes |
| `h` | hours |
| `d` | days |

Examples: `5m`, `30m`, `1h`, `2d`

## Examples

### Monitor a news SERP hourly

```bash
scrapingbee schedule --every 1h --name python-news google "python news"
```

### Refresh product prices daily with --update-csv

```bash
scrapingbee schedule --every 1d --name prices \
  amazon-product --input-file asins.csv --input-column asin --update-csv
```

### Scrape a page every 30 minutes

```bash
scrapingbee schedule --every 30m --name dashboard scrape "https://example.com/dashboard" --output-file latest.html
```

### Crawl a site weekly

```bash
scrapingbee schedule --every 7d --name docs-crawl crawl "https://docs.example.com" \
  --output-dir crawl-runs/ --max-pages 500
```

### List active schedules

```bash
scrapingbee schedule --list
```

### Stop a named schedule

```bash
scrapingbee schedule --stop python-news
```

### Stop all schedules

```bash
scrapingbee schedule --stop all
```

## Notes

- Schedules are registered as cron jobs and persist across terminal sessions and reboots.
- Use `--list` to see all active scrapingbee schedules with their interval and running time.
- Use `--stop NAME` to remove a specific schedule, or `--stop all` to remove all scrapingbee schedules.
- The API key is forwarded automatically from the current session to the cron job.

## Related

- [Batch output layout](../batch/output.md) — manifest.json format including `credits_used`, `latency_ms`
- [Update CSV (--update-csv)](../batch/overview.md) — refresh input data in-place
