# Gemini API

> **Syntax:** use space-separated values — `--option value`, not `--option=value`.

Send a prompt to the ScrapingBee Gemini endpoint. **Credit:** 15 per request. Prompt limit: 8000 characters.

## Parameters

| Flag | Description | Default |
|------|-------------|---------|
| `--add-html` | Include full HTML of the page in results (`true`/`false`). | not sent |
| `--country-code` | Country code for geolocation (ISO 3166-1, e.g. `us`, `gb`). | not sent |
| `--tag` | Optional label included in API response headers. | not sent |

Unlike `chatgpt`, Gemini has **no `--search` flag** (web grounding is on by default upstream).

Plus global flags: `--output-file`, `--verbose`, `--output-dir`, `--concurrency`, `--retries`, `--backoff`.

## Command

```bash
scrapingbee gemini --output-file response.txt "Explain quantum computing in one sentence"
scrapingbee gemini "Latest AI news"
scrapingbee gemini "Hello" --country-code gb
```

Prompt is the positional argument; multiple words are joined. Use **`--output-file path`** (before or after command) so the response is not streamed into context.

## Batch

`--input-file` (one prompt per line) + `--output-dir`. Output: `N.json` in batch folder.

## Output

JSON: `results_markdown`, `results_text`, `citations` (array of `title`/`url`/`text`/`description`), `prompt`, and `full_html` (populated only with `--add-html true`). Run `scrapingbee usage` before large batches.

```json
{
  "prompt": "Explain quantum computing in one sentence",
  "results_text": "Quantum computing uses qubits...",
  "results_markdown": "Quantum computing uses **qubits**...",
  "citations": [
    {"title": "Quantum computing", "url": "https://...", "text": "...", "description": "..."}
  ],
  "full_html": ""
}
```
