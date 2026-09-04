# YouTube Subtitles API

> **Syntax:** use space-separated values — `--option value`, not `--option=value`.

Fetch video subtitles (captions/transcript) with timestamps. JSON output. **Credit:** 5 per request. Use **`--output-file file.json`** (before or after command).

## Command

```bash
scrapingbee youtube-subtitles --output-file subtitles.json dQw4w9WgXcQ
```

## Parameters

| Flag | Values | Notes |
|------|--------|-------|
| `--language` | ISO language code (`en`, `fr`, ...) | A language with no matching subtitles returns 404. |
| `--subtitle-origin` | `auto-generated`, `uploader-provided` | Filter by subtitle source. |

Plus global flags (`--output-file`, `--verbose`, `--output-dir`, `--concurrency`, `--retries`, `--backoff`).

## Batch

`--input-file` (one video ID **or full YouTube URL** per line) + `--output-dir`. Output: `N.json`.

Full YouTube URLs (`https://www.youtube.com/watch?v=...`, `youtu.be/...`, `/shorts/...`) are automatically resolved to video IDs — pipe `--extract-field results.link youtube-search` output directly.

## Output

JSON: `subtitles.auto_generated` and `subtitles.uploader_provided`, keyed by language, each a list of timestamped text runs.

```json
{
  "subtitles": {
    "auto_generated": {
      "en": [
        {
          "start_ms": "18800",
          "d_duration_ms": "7160",
          "snippet": {"runs": [{"text": "We're"}, {"text": " no"}, {"text": " strangers"}]}
        }
      ]
    },
    "uploader_provided": {}
  }
}
```
