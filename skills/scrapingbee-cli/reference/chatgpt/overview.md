# ChatGPT API

Send a prompt to the ScrapingBee ChatGPT endpoint. **No command-specific parameters**; only global flags (`--output-file`, `--verbose`, `--output-dir`, `--concurrency`, `--retries`, `--backoff`). **Credit:** 15 per request.

## Command

```bash
scrapingbee --output-file response.txt chatgpt "Explain quantum computing in one sentence"
```

Prompt is the positional argument; multiple words are joined. Use **`--output-file path`** (before command) so the response is not streamed into context.

## Batch

`--input-file` (one prompt per line) + `--output-dir`. Output: `N.json` in batch folder.

## Output

JSON: `results_markdown`, `results_text`, `results_json` (structured blocks), `llm_model`, `prompt`. Optional `full_html` if `add_html true`. Run `scrapingbee usage` before large batches.
