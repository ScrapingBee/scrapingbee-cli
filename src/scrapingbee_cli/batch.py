"""Batch mode: read input file, run concurrent requests, write output (async)."""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from .client import Client, parse_usage
from .config import get_api_key

# Map Content-Type (main part, lowercased) to file extension for batch output.
CONTENT_TYPE_EXTENSION: dict[str, str] = {
    "application/json": "json",
    "application/ld+json": "json",
    "text/html": "html",
    "text/markdown": "md",
    "text/plain": "txt",
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/svg+xml": "svg",
    "application/pdf": "pdf",
    "application/zip": "zip",
}

# HTML API (scrape) can return multiple types. Put images in screenshots/, other binary in files/.
SCREENSHOT_EXTENSIONS = frozenset({"png", "jpg", "gif", "webp"})
BINARY_FILE_EXTENSIONS = frozenset({"pdf", "zip"})

# Known file extensions for URL path detection (e.g. index.html, sitemap.xml, archive.zip).
URL_PATH_EXTENSIONS = frozenset({
    "html", "htm", "xml", "json", "zip", "pdf", "md", "txt", "svg",
    "png", "jpg", "jpeg", "gif", "webp", "ico", "css", "js",
})


def _batch_subdir_for_extension(ext: str) -> str | None:
    """Return 'screenshots', 'files', or None (write to batch root). Only for scrape-like output."""
    if ext in SCREENSHOT_EXTENSIONS:
        return "screenshots"
    if ext in BINARY_FILE_EXTENSIONS:
        return "files"
    return None


def extension_from_content_type(headers: dict) -> str:
    """Return file extension from response headers, or 'unidentified.txt' if unknown."""
    raw = ""
    for k, v in headers.items():
        if k.lower() == "content-type" and v:
            raw = v if isinstance(v, str) else str(v)
            break
    main = raw.split(";")[0].strip().lower()
    if main in CONTENT_TYPE_EXTENSION:
        return CONTENT_TYPE_EXTENSION[main]
    return "unidentified.txt"


def _looks_like_json(body: bytes) -> bool:
    """True if body starts with { or [ and next token looks like JSON (not e.g. Markdown [text](url))."""
    if not body:
        return False
    body = body.lstrip()
    if body[:1] not in (b"{", b"["):
        return False
    rest = body[1:].lstrip()
    # Empty object {} or array [] or just "{" / "[" (minimal valid start)
    if not rest:
        return True
    # After [ or {, next non-whitespace must be a JSON value starter or closing } ]
    first = rest[0:1]
    return first in (
        b'"', b"{", b"[", b"}", b"]",
        b"0", b"1", b"2", b"3", b"4", b"5", b"6", b"7", b"8", b"9",
        b"-", b"n", b"t", b"f",
    )


def _looks_like_markdown(body: bytes) -> bool:
    """True if body looks like Markdown (e.g. [text](url) link syntax). ScrapingBee may not send correct Content-Type."""
    if not body or body[:1] != b"[":
        return False
    # Markdown link pattern ]( in first 2KB is a strong signal
    chunk = body.lstrip()[:2048]
    return b"](" in chunk


def extension_from_body_sniff(body: bytes) -> str | None:
    """Return extension if body has obvious magic bytes; else None (API type can be wrong)."""
    if not body:
        return None
    body = body.lstrip()
    if body.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if body[:2] == b"\xff\xd8":
        return "jpg"
    if body[:4] == b"GIF8":
        return "gif"
    if len(body) >= 12 and body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return "webp"
    if _looks_like_json(body):
        return "json"
    if _looks_like_markdown(body):
        return "md"
    if body.startswith(b"<!") or body.startswith(b"<html"):
        return "html"
    return None


def extension_for_scrape(headers: dict, body: bytes) -> str:
    """Infer extension for scrape: body sniff first, then Content-Type, else unidentified.txt."""
    from_header = extension_from_content_type(headers)
    sniffed = extension_from_body_sniff(body)
    if sniffed is not None:
        return sniffed
    if from_header != "unidentified.txt":
        return from_header
    return "unidentified.txt"


def extension_from_url_path(url: str) -> str | None:
    """Return file extension from the last path segment of URL, or None if unknown.
    E.g. index.html -> html, sitemap.xml -> xml, archive.zip -> zip.
    """
    path = urlparse(url).path.strip("/")
    if not path:
        return None
    last = path.split("/")[-1]
    if "." not in last:
        return None
    _, _, ext = last.rpartition(".")
    ext = ext.lower().split("?")[0]
    return ext if ext in URL_PATH_EXTENSIONS else None


def extension_for_crawl(
    url: str,
    headers: dict,
    body: bytes,
    preferred_extension: str | None,
) -> str:
    """Extension for crawl: 1) preferred (from scrape params), 2) URL path, 3) body/Content-Type."""
    if preferred_extension:
        return preferred_extension
    from_url = extension_from_url_path(url)
    if from_url is not None:
        return from_url
    return extension_for_scrape(headers, body)


def read_input_file(path: str) -> list[str]:
    """Read non-empty trimmed lines from file (one input per line)."""
    with open(path, encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    if not lines:
        raise ValueError(f'input file "{path}" has no non-empty lines')
    return lines


async def _fetch_usage_async(api_key: str) -> dict:
    """Fetch usage from API (async)."""
    async with Client(api_key) as client:
        body, _, code = await client.usage()
        if code != 200:
            raise RuntimeError(f"usage API returned HTTP {code}")
        return parse_usage(body)


def get_batch_usage(api_key_flag: str | None) -> dict:
    """Return usage info (max_concurrency, credits) from usage API."""
    key = get_api_key(api_key_flag)
    return asyncio.run(_fetch_usage_async(key))


def validate_batch_run(user_concurrency: int, num_inputs: int, usage: dict) -> None:
    """Raise ValueError if batch should not run (concurrency or credits)."""
    max_concurrency = usage.get("max_concurrency", 5)
    if user_concurrency > 0 and user_concurrency > max_concurrency:
        raise ValueError(
            f"concurrency {user_concurrency} exceeds your plan limit of {max_concurrency} "
            "(check with: scrapingbee usage)"
        )
    credits = usage.get("credits", 0)
    if credits > 0 and num_inputs > credits:
        raise ValueError(
            f"not enough credits: {num_inputs} requested, {credits} available "
            "(check with: scrapingbee usage)"
        )


def resolve_batch_concurrency(user_concurrency: int, usage: dict, num_inputs: int) -> int:
    """Return concurrency to use: user value if set, else usage limit (at least 1)."""
    if user_concurrency > 0:
        return user_concurrency
    from_usage = usage.get("max_concurrency", 5)
    return max(1, from_usage) if from_usage else 5


@dataclass
class BatchResult:
    """Result of one batch item."""

    index: int
    input: str
    body: bytes
    headers: dict
    status_code: int
    error: Exception | None
    # When set, use this extension (per-documentation type). When None, infer for scrape only.
    expected_extension: str | None = None


AsyncBatchFn = Callable[[str], Awaitable[tuple[bytes, dict, int, Exception | None, str | None]]]


async def run_batch_async(
    inputs: list[str],
    concurrency: int,
    async_fn: AsyncBatchFn,
    *,
    from_user: bool = False,
) -> list[BatchResult]:
    """Run async_fn for each input with up to concurrency in flight; preserve order."""
    concurrency = min(max(1, concurrency), len(inputs))
    source = "from --concurrency" if from_user else "from usage API"
    print(f"Batch: {len(inputs)} items, concurrency {concurrency} ({source})", file=sys.stderr)
    sem = asyncio.Semaphore(concurrency)

    async def run_one(i: int, inp: str) -> tuple[int, BatchResult]:
        async with sem:
            try:
                body, headers, status_code, err, expected_ext = await async_fn(inp)
            except Exception as e:
                body, headers, status_code, err, expected_ext = b"", {}, 0, e, None
            return i, BatchResult(
                index=i,
                input=inp,
                body=body,
                headers=headers,
                status_code=status_code,
                error=err,
                expected_extension=expected_ext,
            )

    tasks = [run_one(i, inp) for i, inp in enumerate(inputs)]
    ordered = await asyncio.gather(*tasks)
    return [result for _, result in ordered]


def default_batch_output_dir() -> str:
    """Default folder name for batch output (batch_<timestamp>)."""
    return "batch_" + datetime.now().strftime("%Y%m%d_%H%M%S")


def write_batch_output_to_dir(
    results: list[BatchResult],
    output_dir: str | None,
    verbose: bool,
) -> str:
    """Write 1.<ext>, 2.<ext>, ... (ext per docs or inferred for scrape) and N.err for failures."""
    output_dir = output_dir or default_batch_output_dir()
    abs_dir = str(Path(output_dir).resolve())
    os.makedirs(abs_dir, exist_ok=True)
    for result in results:
        n = result.index + 1
        if result.error is not None:
            print(f"Item {n} ({result.input!r}): {result.error}", file=sys.stderr)
            if result.body:
                err_path = os.path.join(abs_dir, f"{n}.err")
                with open(err_path, "wb") as out_file:
                    out_file.write(result.body)
            continue
        if verbose:
            print(f"Item {n}: HTTP {result.status_code}", file=sys.stderr)
        # Same order as crawl: preferred (expected) → URL path → body/Content-Type
        ext = extension_for_crawl(
            result.input,
            result.headers,
            result.body,
            result.expected_extension,
        )
        subdir = _batch_subdir_for_extension(ext)
        if subdir:
            out_dir = os.path.join(abs_dir, subdir)
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, f"{n}.{ext}")
        else:
            out_path = os.path.join(abs_dir, f"{n}.{ext}")
        with open(out_path, "wb") as out_file:
            out_file.write(result.body)
    return abs_dir
