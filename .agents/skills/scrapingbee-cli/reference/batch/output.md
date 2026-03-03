# Batch output layout

One file per input line (N = line number).

**Scrape:** Extension from body sniff then Content-Type; unknown → `N.bin`. PNG/jpg/gif/webp → **`screenshots/`** subfolder; other binary (pdf, zip) → **`files/`**; JSON/HTML/text → batch root (`1.json`, `2.html`, etc.).

**Google, fast-search, amazon, walmart, youtube, chatgpt:** Always **`N.json`** in batch root.

**Failures:** Each failed item is reported on stderr. **`N.err`** in the batch folder contains the error message and (if the API returned a body) that response body

**manifest.json:** Written to the output directory for every batch or crawl run. Maps each input to its output file and metadata:

```json
{
  "https://example.com": {
    "file": "1.html",
    "fetched_at": "2025-01-01T00:00:00+00:00",
    "http_status": 200,
    "credits_used": 5,
    "latency_ms": 1234,
    "content_md5": "d41d8cd98f00b204e9800998ecf8427e"
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `file` | `string \| null` | Relative path to the output file. `null` when `--diff-dir` detects unchanged content. |
| `fetched_at` | `string` | ISO-8601 UTC timestamp of the request. |
| `http_status` | `int` | HTTP status code from the API. |
| `credits_used` | `int \| null` | Credits consumed (from `Spb-Cost` header). `null` for SERP endpoints. |
| `latency_ms` | `int \| null` | Request latency in milliseconds. |
| `content_md5` | `string` | MD5 hash of response body. Used by `--diff-dir` for change detection. |
| `unchanged` | `bool` | Only present when `--diff-dir` detects identical content. |

Completion: stdout prints `Batch complete. Output written to <absolute path>`.
