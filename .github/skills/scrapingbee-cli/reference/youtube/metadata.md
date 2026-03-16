# YouTube Metadata API

> **Syntax:** use space-separated values — `--option value`, not `--option=value`.

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

JSON: title, description, view_count, uploader, duration (seconds as int), like_count, upload_date (int YYYYMMDD), video_id, age_limit, categories, channel_id, channel_url, comment_count, is_live, tags, thumbnails, uploader_id, uploader_url, etc. Batch: output is `N.json` in batch folder.

```json
{
  "title": "Video Title",
  "description": "Video description...",
  "view_count": 1500000000,
  "uploader": "Channel Name",
  "duration": 213,
  "like_count": 15000000,
  "upload_date": 20091025,
  "video_id": "dQw4w9WgXcQ",
  "age_limit": 0,
  "categories": ["Music"],
  "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
  "comment_count": 2800000,
  "is_live": false,
  "tags": ["rick astley", "never gonna give you up"]
}
```
