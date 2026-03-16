# YouTube Search API

> **Syntax:** use space-separated values — `--option value`, not `--option=value`.

Search YouTube videos (or channels, playlists, movies). JSON output. **Credit:** 5 per request. Use **`--output-file file.json`** (before or after command).

## Command

```bash
scrapingbee youtube-search --output-file yt-search.json "tutorial python"
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `--upload-date` | string | `today`, `last-hour`, `this-week`, `this-month`, `this-year`. |
| `--type` | string | `video`, `channel`, `playlist`, `movie`. |
| `--duration` | choice | Duration filter: `short` (<4 min), `medium` (4-20 min), `long` (>20 min). Raw values `"<4"`, `"4-20"`, `">20"` also accepted. |
| `--sort-by` | string | `relevance`, `rating`, `view-count`, `upload-date`. |
| `--hd` / `--4k` / `--subtitles` / `--creative-commons` / `--live` / `--360` / `--3d` / `--hdr` / `--location` / `--vr180` | true/false | Filters. |

## Pipeline: search → metadata batch

```bash
# Extract video links and fetch full metadata for each (no jq or sed)
scrapingbee youtube-search --extract-field results.link "python asyncio tutorial" > videos.txt
scrapingbee youtube-metadata --output-dir metadata --input-file videos.txt
scrapingbee export --output-file videos.csv --input-dir metadata --format csv
```

`youtube-metadata` accepts full YouTube URLs as well as bare video IDs — both work as batch input.

## Batch

`--input-file` (one query per line) + `--output-dir`. Output: `N.json`.

## Output

JSON: `results` (nested structure: title, link, channel, etc.). See [reference/youtube/search-output.md](reference/youtube/search-output.md).

```json
{
  "results": [
    {
      "title": "Video Title",
      "link": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
      "channel": "Channel Name",
      "duration": "3:33",
      "views": "1.5B views",
      "published": "15 years ago"
    }
  ]
}
```
