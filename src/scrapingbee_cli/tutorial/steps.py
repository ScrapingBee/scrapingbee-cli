"""All tutorial steps — 25 screens from basics to production pipelines."""

from __future__ import annotations

from .runner import Step

# ── Shared constants ───────────────────────────────────────────────────────────

HOME = "https://books.toscrape.com/"
BOOK = "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"

# AI extraction rules reused across steps (key: plain English description).
_RULES_SIMPLE = '{"title":"book title","price":"price of the book"}'
_RULES_FULL = (
    '{"title":"book title",'
    '"price":"price of the book",'
    '"rating":"star rating out of 5",'
    '"availability":"stock availability"}'
)


def get_chapter_list() -> list[tuple[int, str, list[Step]]]:
    """Return chapters as ``[(chapter_num, chapter_name, [steps])]``."""
    chapters: dict[int, tuple[str, list[Step]]] = {}
    for s in STEPS:
        if s.chapter not in chapters:
            chapters[s.chapter] = (s.chapter_name, [])
        chapters[s.chapter][1].append(s)
    return [(num, name, steps) for num, (name, steps) in sorted(chapters.items())]


# ── Steps ──────────────────────────────────────────────────────────────────────

STEPS: list[Step] = [
    # ── Chapter 0: Setup ─────────────────────────────────────────────────────
    Step(
        id="CH00-S01",
        chapter=0,
        chapter_name="Setup",
        title="Save your API key with auth",
        explanation="""\
Before you can scrape, you need a ScrapingBee API key.
If you don't have one, sign up at https://www.scrapingbee.com/

This step saves your key to ~/.config/scrapingbee-cli/.env
so you don't need to pass it every time.""",
        args=["auth"],
        what_to_notice="""\
• Your key is validated against the API before saving
• Once saved, every command picks it up automatically
• You can also set SCRAPINGBEE_API_KEY as an environment variable""",
    ),
    Step(
        id="CH00-S02",
        chapter=0,
        chapter_name="Setup",
        title="Check your credit balance with usage",
        explanation="""\
Every API call costs credits. Before we start, let's see your balance.

Remember this number — at the end of the tutorial, we'll check again
to see how many credits the full walkthrough consumed.""",
        args=["usage"],
        what_to_notice="""\
• max_api_credit — your monthly allowance
• used_api_credit — credits consumed so far this billing cycle
• max_concurrency — how many parallel requests your plan allows""",
    ),
    # ── Chapter 1: First Scrape ──────────────────────────────────────────────
    Step(
        id="CH01-S01",
        chapter=1,
        chapter_name="First Scrape",
        title="Fetch a page with scrape",
        explanation="""\
The scrape command fetches a URL and returns the page content.
ScrapingBee rotates proxies and sets browser-like headers for you —
you just provide the URL.

--render-js false skips the headless browser (1 credit instead of 5).
Use it when the page doesn't need JavaScript to load its content.""",
        args=[
            "scrape",
            HOME,
            "--render-js",
            "false",
            "--output-file",
            "{OUT}/homepage.html",
        ],
        what_to_notice="""\
• The HTML file was saved — open it in a browser to see the page
• This cost 1 credit (no JavaScript rendering)
• ScrapingBee rotated proxies and set headers automatically""",
        preview_file="{OUT}/homepage.html",
    ),
    Step(
        id="CH01-S02",
        chapter=1,
        chapter_name="First Scrape",
        title="Inspect response metadata with --verbose",
        explanation="""\
--verbose prints HTTP metadata before saving the page:
  • HTTP status code (200 = success, 429 = too many concurrent requests, 500 = retry)
  • Credit cost charged for the request
  • Resolved URL (final URL after any redirects)

This is useful for debugging — you can confirm the request succeeded
and see exactly how many credits were consumed, without opening the file.""",
        args=[
            "scrape",
            HOME,
            "--render-js",
            "false",
            "--verbose",
            "--output-file",
            "{OUT}/homepage-verbose.html",
        ],
        what_to_notice="""\
• HTTP Status: 200 confirms the page loaded successfully
• Credit Cost: 1 — the cheapest request type (no JS rendering)
• Resolved URL shows the final URL after redirects""",
    ),
    # ── Chapter 2: AI Extraction ─────────────────────────────────────────────
    Step(
        id="CH02-S01",
        chapter=2,
        chapter_name="AI Extraction",
        title="Extract fields with --ai-extract-rules",
        explanation="""\
--ai-extract-rules accepts a JSON object where each key is a field name
and each value is a plain English description of the data you want.
ScrapingBee uses AI to find and extract the matching data from the page
and returns structured JSON.

Format:  {"fieldName": "description of what to extract"}

No CSS selectors or HTML inspection needed — just describe the data.""",
        args=[
            "scrape",
            BOOK,
            "--ai-extract-rules",
            _RULES_FULL,
            "--output-file",
            "{OUT}/ai-extract-rules.json",
        ],
        what_to_notice="""\
• Response is a clean JSON object with your named fields
• title, price, rating, availability — all extracted by AI
• You described what you wanted in plain English, not CSS selectors""",
        preview_file="{OUT}/ai-extract-rules.json",
    ),
    Step(
        id="CH02-S02",
        chapter=2,
        chapter_name="AI Extraction",
        title="Describe what you want with --ai-query",
        explanation="""\
--ai-query is flexible — ask questions, request summaries, or tell the
AI how to structure its response. The AI reads the page and responds
however you ask it to.

Use --ai-query for questions, summaries, and custom formatting.
Use --ai-extract-rules when you need guaranteed JSON field extraction.""",
        args=[
            "scrape",
            BOOK,
            "--ai-query",
            "book title, price, star rating and stock availability",
            "--output-file",
            "{OUT}/ai-query.json",
        ],
        what_to_notice="""\
• The response matches what you asked — title, price, rating, availability
• The format is flexible — the AI decides how to present it
• Compare with the previous step: --ai-extract-rules gave structured JSON keys""",
        preview_file="{OUT}/ai-query.json",
    ),
    # ── Chapter 3: Screenshot ────────────────────────────────────────────────
    Step(
        id="CH03-S01",
        chapter=3,
        chapter_name="Screenshot",
        title="Capture a viewport screenshot",
        explanation="""\
--screenshot true captures the page as a PNG image using a real
headless browser. The screenshot shows exactly what a user would see.

Screenshots always use JavaScript rendering (headless browser), so
the cost is 5 credits regardless of --render-js setting.

Useful for: visual QA, archiving page state, monitoring layout changes.""",
        args=[
            "scrape",
            HOME,
            "--screenshot",
            "true",
            "--output-file",
            "{OUT}/screenshot.png",
        ],
        what_to_notice="""\
• A real PNG image was saved — open it to see the rendered page
• The headless browser rendered CSS, images, and fonts
• This cost 5 credits — screenshots always use JavaScript rendering""",
    ),
    # ── Chapter 4: Search & APIs ─────────────────────────────────────────────
    Step(
        id="CH04-S01",
        chapter=4,
        chapter_name="Search & APIs",
        title="Query Google with the google command",
        explanation="""\
The google command queries Google Search and returns parsed, structured
JSON — not raw HTML. You get organic results, knowledge panels,
related searches, and more as clean data.

No need to scrape Google yourself — ScrapingBee handles the search
request and returns structured results ready for processing.

Each organic result has: title, url, description, and position.""",
        args=[
            "google",
            "mystery novels bestsellers",
            "--output-file",
            "{OUT}/google.json",
        ],
        what_to_notice="""\
• organic_results is a list — each result has title, url, description
• meta_data shows total result count and search metadata
• No HTML parsing needed — Google results are pre-structured""",
        preview_file="{OUT}/google.json",
    ),
    Step(
        id="CH04-S02",
        chapter=4,
        chapter_name="Search & APIs",
        title="Get AI-generated answers with --search-type ai-mode",
        explanation="""\
--search-type ai-mode enables Google's AI Overview, which synthesizes
answers from multiple sources. You get a summarized answer plus the
sources it drew from, alongside regular organic results.

This combines the breadth of Google Search with AI synthesis —
useful for research, fact-checking, and content generation.""",
        args=[
            "google",
            "best books for learning programming",
            "--search-type",
            "ai-mode",
            "--output-file",
            "{OUT}/google-ai.json",
        ],
        what_to_notice="""\
• Look for an ai_overview key with the AI-generated summary
• Sources are cited — you can trace where the answer came from
• Regular organic_results are included alongside the AI answer""",
        preview_file="{OUT}/google-ai.json",
    ),
    Step(
        id="CH04-S03",
        chapter=4,
        chapter_name="Search & APIs",
        title="Search Amazon products with amazon-search",
        explanation="""\
amazon-search queries Amazon's search results and returns structured
product data. Each result includes title, price, rating, review count,
ASIN (Amazon's unique product ID), and thumbnail URL.

--sort-by controls result ordering: relevance, price-low, price-high,
reviews, bestsellers, newest.""",
        args=[
            "amazon-search",
            "mystery novels",
            "--sort-by",
            "bestsellers",
            "--output-file",
            "{OUT}/amazon-search.json",
        ],
        what_to_notice="""\
• Each product has a structured price, rating, and ASIN
• Use the ASIN with amazon-product to get full product details
• Compare prices across Amazon and Walmart (next chapters)""",
        preview_file="{OUT}/amazon-search.json",
    ),
    Step(
        id="CH04-S04",
        chapter=4,
        chapter_name="Search & APIs",
        title="Search YouTube videos with youtube-search",
        explanation="""\
youtube-search queries YouTube and returns structured video results.
Each result includes title, URL, video ID, view count, channel name,
and publish date.

--type video filters to videos only (excludes channels, playlists).
--sort-by view-count shows the most popular results first.""",
        args=[
            "youtube-search",
            "mystery novel review",
            "--type",
            "video",
            "--sort-by",
            "view-count",
            "--output-file",
            "{OUT}/youtube-search.json",
        ],
        what_to_notice="""\
• Each video has view_count, video_id, channel, and publish_date
• Use youtube-metadata with a video_id to get full details (duration, tags, etc.)
• Structured data — no YouTube HTML scraping needed""",
        preview_file="{OUT}/youtube-search.json",
    ),
    # ── Chapter 5: ChatGPT ───────────────────────────────────────────────────
    Step(
        id="CH05-S01",
        chapter=5,
        chapter_name="ChatGPT",
        title="Query ChatGPT with the chatgpt command",
        explanation="""\
The chatgpt command sends a prompt to ChatGPT and returns the response
as JSON. --search true enables web search, letting ChatGPT access
current information when answering.

This turns your terminal into an AI research assistant — ask questions,
get structured answers, pipe them into your workflow.""",
        args=[
            "chatgpt",
            "What are the top 5 mystery novels for beginners?",
            "--search",
            "true",
            "--output-file",
            "{OUT}/chatgpt.json",
        ],
        what_to_notice="""\
• The response is structured JSON, not plain text
• --search true lets ChatGPT access current web information
• Pipe the output through --smart-extract to pull specific fields""",
        preview_file="{OUT}/chatgpt.json",
    ),
    # ── Chapter 6: Smart Extract ─────────────────────────────────────────────
    Step(
        id="CH06-S01",
        chapter=6,
        chapter_name="Smart Extract",
        title="Extract from any format with --smart-extract",
        explanation="""\
--smart-extract auto-detects the response format (JSON, HTML, XML, CSV,
Markdown, or plain text) and lets you extract data using a path language.

Use ...key to search recursively — it finds every occurrence of a key
at any depth in the document tree. No need to know the exact path.

Here we scrape the homepage as HTML and extract all book titles.""",
        args=[
            "scrape",
            HOME,
            "--render-js",
            "false",
            "--smart-extract",
            "...h3.a.title",
        ],
        what_to_notice="""\
• Extracted 20 book titles directly from raw HTML using the path language
• ...h3 found all <h3> elements, .a navigated into the <a> tag, .title got the attribute
• Works on JSON, HTML, XML, CSV, Markdown — same syntax for any format""",
    ),
    Step(
        id="CH06-S02",
        chapter=6,
        chapter_name="Smart Extract",
        title="Structured output with JSON schema",
        explanation="""\
Pass a JSON object to --smart-extract and each value becomes a path
expression. The output is a structured JSON object with your field names.

This is the same pattern as --ai-extract-rules — but instead of AI,
you use the path language to pinpoint exactly what you want.

Works on all commands: scrape, google, amazon, youtube, chatgpt.""",
        args=[
            "google",
            "scrapingbee web scraping",
            "--smart-extract",
            '{"titles":"organic_results[0:3].title","urls":"organic_results[0:3].url"}',
        ],
        what_to_notice="""\
• Output is a clean JSON object with your named fields
• organic_results[0:3] selected the first 3 results, .title/.url extracted the fields
• Same format as --ai-extract-rules — familiar if you use that feature""",
    ),
    Step(
        id="CH06-S03",
        chapter=6,
        chapter_name="Smart Extract",
        title="Filter and drill with the path language",
        explanation="""\
The path language has powerful operations for filtering and drilling:
  [=pattern]        filter values by text, glob (*), or regex (/.../)
  [key=pattern]     filter dicts where a key's value matches
  ...key            recursive search at any depth
  [keys] / [values] get all dict keys or values
  ~N                context expansion (N parent levels)

Here we find all links pointing to book catalogue pages.""",
        args=[
            "scrape",
            HOME,
            "--render-js",
            "false",
            "--smart-extract",
            "...a[href=*catalogue*].title",
        ],
        what_to_notice="""\
• Only links matching *catalogue* were included — other links filtered out
• .title extracted the title attribute from each matching <a> element
• [href=*catalogue*] is a key filter: keep <a> elements where href matches""",
    ),
    # ── Chapter 7: Hidden APIs ───────────────────────────────────────────────
    Step(
        id="CH07-S01",
        chapter=7,
        chapter_name="Hidden APIs",
        title="Discover hidden API calls with --json-response",
        explanation="""\
--json-response true captures everything the page does — including xhr:
every background API call the page made during rendering.

Many modern sites load data via hidden internal APIs. The xhr key
captures those requests automatically. Use --smart-extract to drill
straight into the captured data.

Here we scrape httpbin's Swagger UI — it loads its API spec via XHR.""",
        args=[
            "scrape",
            "https://httpbin.scrapingbee.com/",
            "--json-response",
            "true",
            "--render-js",
            "true",
            "--wait",
            "5000",
            "--smart-extract",
            "xhr.body.info",
        ],
        what_to_notice="""\
• Extracted the API info from a hidden XHR request — automatically discovered
• xhr.body drilled through the JSON string in the XHR body
• The page loaded spec.json via JavaScript — we captured the XHR response automatically""",
    ),
    Step(
        id="CH07-S02",
        chapter=7,
        chapter_name="Hidden APIs",
        title="Extract all endpoints from a hidden API",
        explanation="""\
Building on the previous step — now we drill deeper into the captured
API spec to extract just the endpoint names.

xhr.body.paths[keys] means:
  xhr       → the captured XHR requests
  .body     → the response body (auto-parsed from JSON string)
  .paths    → the paths object in the API spec
  [keys]    → just the key names (endpoint paths)

One command: rendered page → hidden API → 52 endpoint names.""",
        args=[
            "scrape",
            "https://httpbin.scrapingbee.com/",
            "--json-response",
            "true",
            "--render-js",
            "true",
            "--wait",
            "5000",
            "--smart-extract",
            "xhr.body.paths[keys]",
        ],
        what_to_notice="""\
• 52 API endpoints extracted from a hidden XHR request
• [keys] returned just the endpoint names, not the full definitions
• From rendered web page to structured API data — in one command""",
    ),
    # ── Chapter 8: Crawling ──────────────────────────────────────────────────
    Step(
        id="CH08-S01",
        chapter=8,
        chapter_name="Crawling",
        title="Follow links automatically with crawl",
        explanation="""\
The crawl command starts at a URL and follows links to discover pages.
Each discovered page is fetched and saved to --output-dir.

--max-pages limits total pages (controls credit spend).
--max-depth limits how far from the start URL to follow.

Unlike scrape (one URL), crawl discovers and fetches automatically.""",
        args=[
            "crawl",
            HOME,
            "--max-pages",
            "5",
            "--max-depth",
            "1",
            "--output-dir",
            "{OUT}/crawl-basic/",
        ],
        stream_output=True,
        what_to_notice="""\
• More files than --max-pages? That's normal — the crawler may receive
  extra responses from concurrent requests already in flight when the limit is hit
• Each page saved as a separate file in crawl-basic/
• The crawler followed links from the homepage to discover new pages""",
    ),
    Step(
        id="CH08-S02",
        chapter=8,
        chapter_name="Crawling",
        title="Stay on-topic with --include-pattern",
        explanation="""\
--include-pattern restricts the crawler to URLs matching a regex pattern.
Only pages whose URL matches the pattern will be fetched.

This keeps your crawl focused — on a site with thousands of pages, you
only fetch the ones that matter. Unmatched URLs are discovered but
not followed.""",
        args=[
            "crawl",
            HOME,
            "--max-pages",
            "10",
            "--include-pattern",
            "catalogue/",
            "--output-dir",
            "{OUT}/crawl-books/",
        ],
        stream_output=True,
        what_to_notice="""\
• Only URLs containing catalogue/ were fetched
• The crawl summary shows how many pages were fetched
• Use --exclude-pattern to skip URLs matching a pattern instead""",
    ),
    # ── Chapter 9: Batch & Export ────────────────────────────────────────────
    Step(
        id="CH09-S01",
        chapter=9,
        chapter_name="Batch & Export",
        title="Scrape many URLs at once with --input-file",
        explanation="""\
Batch mode scrapes a list of URLs from a text file, one URL per line.
Each URL is fetched concurrently and results are saved to --output-dir.

--input-file {OUT}/urls.txt  — source file (created at tutorial start)
--output-dir {OUT}/batch/    — each URL's response saved as its own file
--concurrency 3              — fetch up to 3 URLs simultaneously

We include --ai-extract-rules so each file is a JSON object — this lets
the export command convert the results into CSV.""",
        args=[
            "scrape",
            "--input-file",
            "{OUT}/urls.txt",
            "--ai-extract-rules",
            _RULES_SIMPLE,
            "--output-dir",
            "{OUT}/batch/",
            "--concurrency",
            "3",
        ],
        stream_output=True,
        what_to_notice="""\
• Each URL gets its own output file in batch/
• The progress bar shows completed / total / errors in real time
• Concurrency controls how many URLs are fetched simultaneously""",
    ),
    Step(
        id="CH09-S02",
        chapter=9,
        chapter_name="Batch & Export",
        title="Continue interrupted batches with --resume",
        explanation="""\
Large batch jobs can be interrupted — network issues, API limits, Ctrl+C.
--resume makes batches safe to restart: before fetching a URL, it checks
whether an output file for that URL already exists in --output-dir.
If it does, that URL is skipped (no request, no credits spent).

We just ran this batch, so all 5 files exist — every URL is skipped
without making a request.""",
        args=[
            "scrape",
            "--input-file",
            "{OUT}/urls.txt",
            "--output-dir",
            "{OUT}/batch/",
            "--concurrency",
            "3",
            "--resume",
        ],
        stream_output=True,
        what_to_notice="""\
• All 5 URLs show as skipped — no requests made, files already existed
• Zero credits spent — --resume only fetches what's missing
• Essential for production jobs: safe to restart after any interruption""",
        prereq_path="{OUT}/batch/",
        prereq_step_id="CH09-S01",
        prereq_glob="[0-9]*.json",
        prereq_hint="Batch output from the previous step is needed",
    ),
    Step(
        id="CH09-S03",
        chapter=9,
        chapter_name="Batch & Export",
        title="Export batch results to CSV",
        explanation="""\
The export command reads batch output files and merges them into a
single CSV or NDJSON file.

This completes the pipeline:
  1. Batch scraped 5 URLs with AI extraction
  2. Each result saved as JSON in batch/
  3. Export merged all results into one CSV file""",
        args=[
            "export",
            "--input-dir",
            "{OUT}/batch/",
            "--format",
            "csv",
            "--output-file",
            "{OUT}/results.csv",
        ],
        what_to_notice="""\
• All 5 results merged into one CSV file with columns: _url, title, price
• Each row is one book — ready to open in Excel or Google Sheets
• The full pipeline: batch scrape → AI extraction → CSV export in 3 commands""",
        preview_file="{OUT}/results.csv",
        prereq_path="{OUT}/batch/",
        prereq_step_id="CH09-S01",
        prereq_glob="[0-9]*.json",
        prereq_hint="Batch output from the earlier step is needed",
    ),
    Step(
        id="CH09-S04",
        chapter=9,
        chapter_name="Batch & Export",
        title="Refresh data in-place with --update-csv",
        explanation="""\
--update-csv re-scrapes every URL in an existing CSV file and overwrites
it with fresh data. URLs are read from the first column by default —
use --input-column to specify a different column name or index.

This is the monitoring workflow: export once, then schedule --update-csv
to keep the data current. Prices, stock, ratings — always up to date.""",
        args=[
            "scrape",
            "--input-file",
            "{OUT}/results.csv",
            "--input-column",
            "_url",
            "--ai-extract-rules",
            _RULES_SIMPLE,
            "--update-csv",
            "--concurrency",
            "3",
        ],
        stream_output=True,
        what_to_notice="""\
• The CSV was updated in-place — same file, fresh data
• Each row was re-scraped and the extracted fields were refreshed
• Schedule this daily to monitor prices, stock, or any changing data""",
        prereq_path="{OUT}/results.csv",
        prereq_step_id="CH09-S03",
        prereq_hint="The CSV file from the export step is needed",
    ),
    # ── Chapter 10: Wrap-up ──────────────────────────────────────────────────
    Step(
        id="CH10-S01",
        chapter=10,
        chapter_name="Wrap-up",
        title="Review your total credit usage",
        explanation="""\
Let's check your credit balance again. Compare the used_api_credit
with what you saw at the start of the tutorial (step 2) to see how
many credits the entire walkthrough consumed.

Most steps cost 1-5 credits. The full tutorial typically uses around
100-150 credits depending on API response times and retries.""",
        args=["usage"],
        what_to_notice="""\
• Compare used_api_credit with step 2 — that's your tutorial cost
• max_concurrency shows your plan's parallel request limit
• Credits renew on your renewal_subscription_date""",
    ),
    Step(
        id="CH10-S02",
        chapter=10,
        chapter_name="Wrap-up",
        title="Clear saved credentials with logout",
        explanation="""\
The logout command removes your saved API key from the config file.
Use it when you're done or switching accounts.

That's the end of the tutorial! You've seen scraping, AI extraction,
smart extract, screenshots, search APIs, ChatGPT, hidden API discovery,
crawling, batch processing, and CSV export.

For the full documentation, visit:
  https://www.scrapingbee.com/documentation/cli/""",
        args=["logout"],
        what_to_notice="""\
• Your API key has been removed from ~/.config/scrapingbee-cli/.env
• Run scrapingbee auth to re-authenticate anytime
• That's it — you've completed the tutorial!""",
    ),
]
