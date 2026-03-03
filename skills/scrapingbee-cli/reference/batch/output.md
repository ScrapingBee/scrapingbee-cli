# Batch output layout

One file per input line (N = line number).

**Scrape:** Extension from body sniff then Content-Type; unknown → `N.bin`. PNG/jpg/gif/webp → **`screenshots/`** subfolder; other binary (pdf, zip) → **`files/`**; JSON/HTML/text → batch root (`1.json`, `2.html`, etc.).

**Google, fast-search, amazon, walmart, youtube, chatgpt:** Always **`N.json`** in batch root.

**Failures:** Each failed item is reported on stderr. **`N.err`** in the batch folder contains the error message and (if the API returned a body) that response body.

Completion: stdout prints `Batch complete. Output written to <absolute path>`.

## manifest.json

Every batch run writes a `manifest.json` to the output folder:

```json
{
  "https://example.com": {
    "file": "1.html",
    "fetched_at": "2025-01-15T10:30:00",
    "http_status": 200,
    "credits_used": 5,
    "latency_ms": 1234
  },
  "https://example2.com": {
    "file": "2.html",
    "fetched_at": "2025-01-15T10:30:02",
    "http_status": 200,
    "credits_used": 5,
    "latency_ms": 876,
    "unchanged": true
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
| `unchanged` | `true` when `--diff-dir` was used and content matched the previous run |

The manifest is used by `--resume` to skip already-completed items and by `--diff-dir` for change detection.
