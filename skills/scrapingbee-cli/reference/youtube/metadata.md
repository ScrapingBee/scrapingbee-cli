# YouTube Metadata API

Fetch video metadata (title, channel, duration, views, likes, etc.). JSON output. **Credit:** 5 per request. Use **`--output-file file.json`** (before command).

## Command

```bash
scrapingbee --output-file metadata.json youtube-metadata dQw4w9WgXcQ
```

No command-specific parameters; only global flags (`--output-file`, `--verbose`, `--output-dir`, `--concurrency`, `--retries`, `--backoff`).

## Batch

`--input-file` (one video ID per line) + `--output-dir`. Output: `N.json`.

## Output

JSON: title, description, views, channel, duration, etc. See [reference/youtube/metadata-output.md](reference/youtube/metadata-output.md).
