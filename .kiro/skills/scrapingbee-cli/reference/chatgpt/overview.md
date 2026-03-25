# ChatGPT API

> **Syntax:** use space-separated values — `--option value`, not `--option=value`.

Send a prompt to the ScrapingBee ChatGPT endpoint. **Credit:** 15 per request.

## Parameters

| Flag | Description | Default |
|------|-------------|---------|
| `--search` | Enable web search to enhance the response (`true`/`false`). Only `true` sends the param; `false` is ignored. | not sent |
| `--add-html` | Include full HTML of the page in results (`true`/`false`). | not sent |
| `--country-code` | Country code for geolocation (ISO 3166-1, e.g. `us`, `gb`). | not sent |

Plus global flags: `--output-file`, `--verbose`, `--output-dir`, `--concurrency`, `--retries`, `--backoff`.

## Command

```bash
scrapingbee chatgpt --output-file response.txt "Explain quantum computing in one sentence"
scrapingbee chatgpt "Latest AI news" --search true
scrapingbee chatgpt "Hello" --country-code gb
```

Prompt is the positional argument; multiple words are joined. Use **`--output-file path`** (before or after command) so the response is not streamed into context.

## Batch

`--input-file` (one prompt per line) + `--output-dir`. Output: `N.json` in batch folder.

## Output

JSON: `results_markdown`, `results_text`, `results_json` (structured blocks), `llm_model`, `prompt`. Run `scrapingbee usage` before large batches.

```json
{
  "results_markdown": "Quantum computing uses qubits...",
  "results_text": "Quantum computing uses qubits...",
  "results_json": [{"type": "text", "text": "Quantum computing uses qubits..."}],
  "llm_model": "gpt-4o",
  "prompt": "Explain quantum computing in one sentence"
}
```
