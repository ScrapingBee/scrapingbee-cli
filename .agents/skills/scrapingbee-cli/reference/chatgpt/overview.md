# ChatGPT API

Send a prompt to the ScrapingBee ChatGPT endpoint. **No command-specific parameters**; only global flags (`--output-file`, `--verbose`, `--output-dir`, `--concurrency`, `--retries`, `--backoff`). **Credit:** 15 per request.

## Command

```bash
scrapingbee chatgpt --output-file response.txt "Explain quantum computing in one sentence"
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
