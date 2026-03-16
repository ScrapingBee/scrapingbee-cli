# YouTube search output

**`scrapingbee youtube-search`** returns JSON: `results` (array of video objects), `search` (query).

Batch: output is `N.json` in batch folder. See [reference/batch/output.md](reference/batch/output.md).

## Schema

```json
{
  "results": [
    {
      "link": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
      "video_id": "dQw4w9WgXcQ",
      "title": "Never Gonna Give You Up",
      "channel": "Rick Astley",
      "views": "1.5B views",
      "published": "15 years ago",
      "duration": "3:33"
    }
  ],
  "search": "never gonna give you up"
}
```

Use `--extract-field results.link` to pipe into `youtube-metadata` for full details.
