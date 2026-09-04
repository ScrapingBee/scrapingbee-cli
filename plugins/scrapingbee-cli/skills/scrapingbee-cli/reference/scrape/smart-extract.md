# Smart extraction (`--smart-extract`)

Reach for this whenever you need part of a response rather than all of it. It costs nothing on top
of the request, unlike `--ai-extract-rules` which adds 5 credits — so prefer a path expression when
the fields can be addressed by path, and save AI extraction for fields that need judgement.


Use `--smart-extract` to provide your LLM just the data it needs from any web page — instead of feeding the entire HTML/markdown/text, extract only the relevant section using a path expression. The result: smaller context window usage, lower token cost, and significantly better LLM output quality.

`--smart-extract` auto-detects the response format (JSON, HTML, XML, CSV, Markdown, plain text) and applies the path expression accordingly. It works on every command — `scrape`, `google`, `amazon-product`, `amazon-pricing`, `amazon-search`, `walmart-product`, `walmart-search`, `youtube-search`, `youtube-metadata`, `youtube-subtitles`, `chatgpt`, `gemini`, and `crawl`.

### Path language reference

| Syntax | Meaning | Example |
|--------|---------|---------|
| `.key` | Select a key (JSON/XML) or heading (Markdown/text) | `.product` |
| `[keys]` | Select all keys at current level | `[keys]` |
| `[values]` | Select all values at current level | `[values]` |
| `...key` | Recursive search — find `key` at any depth | `...price` |
| `[=filter]` | Filter nodes by value or attribute | `[=in-stock]` |
| `[!=pattern]` | Negation filter — exclude values/dicts matching a pattern | `...div[class!=sidebar]` |
| `[*=pattern]` | Glob key filter — match dicts where any key's value matches | `...*[*=faq]` |
| `~N` | Context expansion — include N surrounding siblings/lines; chainable anywhere in path | `...text[=*$49*]~2.h3` |

**JSON schema mode:** Pass a JSON object where each value is a path expression. Returns structured output matching your schema exactly:
```
--smart-extract '{"field": "path.expression"}'
```

### Extract product data from an e-commerce page

Instead of passing a full product page (50-100k tokens of HTML) into your context, extract just what you need:

```bash
scrapingbee scrape "https://store.com/product/widget-pro" --return-page-markdown true \
  --smart-extract '{"name": "...title", "price": "...price", "specs": "...specifications", "reviews": "...reviews"}'
# Returns: {"name": "Widget Pro", "price": "$49.99", "specs": "...", "reviews": "..."}
# Typically under 1k tokens — feed directly to your LLM.
```

### Extract search results from a Google response

Pull only the organic result URLs and titles, discarding ads, metadata, and formatting:

```bash
scrapingbee google "best project management tools" \
  --smart-extract '{"urls": "...organic_results...url", "titles": "...organic_results...title"}'
```

### JSON schema mode for structured extraction

Map your desired output fields to path expressions for clean, predictable output:

```bash
scrapingbee amazon-product "B09V3KXJPB" \
  --smart-extract '{"title": "...name", "price": "...price", "rating": "...rating", "availability": "...availability"}'
# Returns a flat JSON object with exactly the fields you specified.
```

### Context expansion with `~N`

When your LLM needs surrounding context for accurate summarization or reasoning, use `~N` to include neighboring sections:

```bash
scrapingbee scrape "https://docs.example.com/api/auth" --return-page-markdown true \
  --smart-extract '...authentication~3'
# Returns the "authentication" section plus 3 surrounding sections.
# Provides enough context for your LLM to answer follow-up questions.
```

This is what sets ScrapingBee CLI apart from other scraping tools — it is not just scraping, it is intelligent extraction that speaks the language of AI agents. Instead of dumping raw web content into your prompt, `--smart-extract` delivers precisely the data your model needs.

