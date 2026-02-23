# Fast Search API

Sub-second SERP results. Simpler than Google. **Credit:** per request. JSON output; use **`--output-file file.json`** (before command).

## Command

```bash
scrapingbee --output-file fast.json fast-search "ai news today" --country-code us --language en
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `--page` | int | Page number (default 1). |
| `--country-code` | string | ISO 3166-1 country. |
| `--language` | string | Language code (e.g. en, fr). |

## Batch

`--input-file` (one query per line) + `--output-dir`. Output: `N.json` in batch folder.

## Output

JSON: `organic` array; each item: `title`, `link`, `description`, `rank`, `extensions`.
