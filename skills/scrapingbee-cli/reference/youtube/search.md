# YouTube Search API

Search YouTube videos (or channels, playlists, movies). JSON output. **Credit:** 5 per request. Use **`--output-file file.json`** (before command).

## Command

```bash
scrapingbee --output-file yt-search.json youtube-search "tutorial python"
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `--upload-date` | string | `today`, `last_hour`, `this_week`, `this_month`, `this_year`. |
| `--type` | string | `video`, `channel`, `playlist`, `movie`. |
| `--duration` | string | Under 4 min, 4–20 min, over 20 min. |
| `--sort-by` | string | `relevance`, `rating`, `view_count`, `upload_date`. |
| `--hd` / `--4k` / `--subtitles` / `--creative-commons` / `--live` / `--360` / `--3d` / `--hdr` / `--location` / `--vr180` | true/false | Filters. |

## Batch

`--input-file` (one query per line) + `--output-dir`. Output: `N.json`.

## Output

JSON: `results` (nested structure: title, link, channel, etc.). See [reference/youtube/search-output.md](reference/youtube/search-output.md).
