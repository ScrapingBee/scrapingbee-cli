# Batch output layout

Output format is controlled by **`--output-format`**. Default (no flag): individual files in `--output-dir`.

## individual files (default)

One file per input line (N = line number). Use with `--output-dir`.

**Scrape:** Extension from body sniff then Content-Type; unknown → `N.bin`. PNG/jpg/gif/webp → **`screenshots/`** subfolder; other binary (pdf, zip) → **`files/`**; JSON/HTML/text → batch root (`1.json`, `2.html`, etc.).

**Google, fast-search, amazon, walmart, youtube, chatgpt:** Always **`N.json`** in batch root.

**Failures:** Each failed item is reported on stderr. **`N.err`** in the batch folder contains the error message and response body.

## csv

`--output-format csv` writes all results to a single CSV (to `--output-dir` path or stdout). Columns: `index`, `input`, `status_code`, `body`, `error`.

```bash
scrapingbee scrape --input-file urls.txt --output-format csv --output-file results.csv
```

## ndjson

`--output-format ndjson` streams each result as a JSON line to stdout as it arrives. Each line: `{"index":1, "input":"...", "status_code":200, "body":{...}, "error":null, "fetched_at":"...", "latency_ms":123}`.

```bash
scrapingbee google --input-file queries.txt --output-format ndjson --output-file results.ndjson
```

Completion: stdout prints `Batch complete: N succeeded, M failed. Output: <path>`.

## manifest.json

Every batch run writes a `manifest.json` to the output folder:

```json
{
  "https://example.com": {
    "file": "1.html",
    "fetched_at": "2025-01-15T10:30:00",
    "http_status": 200,
    "credits_used": 5,
    "latency_ms": 1234,
    "content_md5": "d41d8cd98f00b204e9800998ecf8427e"
  },
  "https://example2.com": {
    "file": "2.html",
    "fetched_at": "2025-01-15T10:30:02",
    "http_status": 200,
    "credits_used": 5,
    "latency_ms": 876,
    "content_md5": "7215ee9c7d9dc229d2921a40e899ec5f"
  }
}
```

| Field | Description |
|-------|-------------|
| `file` | Relative path to the output file within the batch folder |
| `fetched_at` | ISO-8601 timestamp of when the request completed |
| `http_status` | HTTP status code returned by the target site |
| `credits_used` | Credits consumed (from `Spb-Cost` response header) |
| `latency_ms` | Round-trip latency in milliseconds |
| `content_md5` | MD5 hash of the raw response body — use to detect duplicate content or page changes across runs |

The manifest is used by `--resume` to skip already-completed items.
