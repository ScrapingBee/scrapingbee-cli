# Scrape: JS scenario

Run browser actions before returning HTML. Pass **JSON string** to `--js-scenario`. Requires `--render-js true`. Use `--json-response true` for `js_scenario_report`. **Timeout: 40 seconds.** Use space-separated values only, not `=value`.

## Format

```json
{"instructions": [{"wait_for_and_click": "#load-more"}, {"scroll_y": 1000}, {"wait": 2000}], "strict": true}
```

**strict:** true = abort on first failure; false = continue.

## Instructions

| Instruction | Value | Description |
|-------------|--------|-------------|
| click | selector | Click element. |
| wait | ms | Wait duration. |
| wait_for | selector | Wait until element appears. |
| wait_for_and_click | selector | Wait then click. |
| scroll_x / scroll_y | px | Scroll. |
| fill | [selector, value] | Fill input. |
| evaluate | JS code | Run JS; result in evaluate_results when json_response true. |
| infinite_scroll | object | max_count, delay, optional end_click. **Not with stealth proxy.** |

Selectors: CSS by default; `/` prefix = XPath.

## Example

```bash
--js-scenario '{"instructions":[{"click":"#accept-cookies"},{"wait":1000}]}'
```

Output keys when json_response true: [reference/scrape/output.md](reference/scrape/output.md).
