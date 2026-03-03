# YouTube Metadata API

Fetch video metadata (title, channel, duration, views, likes, etc.). JSON output. **Credit:** 5 per request. Use **`--output-file file.json`** (before or after command).

## Command

```bash
scrapingbee youtube-metadata --output-file metadata.json dQw4w9WgXcQ
```

No command-specific parameters; only global flags (`--output-file`, `--verbose`, `--output-dir`, `--concurrency`, `--retries`, `--backoff`).

## Batch

`--input-file` (one video ID **or full YouTube URL** per line) + `--output-dir`. Output: `N.json`.

Full YouTube URLs (`https://www.youtube.com/watch?v=...`, `youtu.be/...`, `/shorts/...`) are automatically resolved to video IDs — pipe `--extract-field results.link youtube-search` output directly.

## Output

JSON: title, description, views, channel, duration, etc. See [reference/youtube/metadata-output.md](reference/youtube/metadata-output.md).

```json
{
  "title": "Video Title",
  "description": "Video description...",
  "views": 1500000000,
  "channel": "Channel Name",
  "duration": "3:33",
  "likes": 15000000,
  "published": "2009-10-25",
  "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
}
```
