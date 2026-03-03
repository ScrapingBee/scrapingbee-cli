"""Shared CLI helpers and constants used by multiple commands."""

from __future__ import annotations

import json
import sys
from typing import Any

import click


def _extract_field_values(data: bytes, path: str) -> bytes:
    """Extract values from JSON data using a simple path expression.

    Supports:
    - ``key.subkey``  — iterate the top-level list at *key*, extract *subkey*
      from each dict item (one value per line).
    - ``key``         — extract the top-level scalar (or list of scalars).

    Returns newline-separated UTF-8 bytes, suitable for use as ``--input-file``.
    Returns *data* unchanged if parsing fails or the path is not found.
    """
    try:
        obj = json.loads(data.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return data

    if "." in path:
        array_key, _, subkey = path.partition(".")
        arr = obj.get(array_key) if isinstance(obj, dict) else None
        if not isinstance(arr, list):
            return b""
        values = [
            str(item[subkey])
            for item in arr
            if isinstance(item, dict) and item.get(subkey) is not None
        ]
    else:
        val = obj.get(path) if isinstance(obj, dict) else None
        if val is None:
            return b""
        if isinstance(val, list):
            values = [str(v) for v in val if v is not None]
        else:
            values = [str(val)]

    return ("\n".join(values) + "\n").encode("utf-8") if values else b""


def _filter_fields(data: bytes, fields: str) -> bytes:
    """Filter JSON output to the specified comma-separated top-level keys.

    Returns filtered JSON bytes.  Returns *data* unchanged if parsing fails.
    """
    keys = [k.strip() for k in fields.split(",") if k.strip()]
    if not keys:
        return data
    try:
        obj = json.loads(data.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return data
    if isinstance(obj, dict):
        filtered: Any = {k: obj[k] for k in keys if k in obj}
    elif isinstance(obj, list):
        filtered = [
            {k: item[k] for k in keys if k in item} if isinstance(item, dict) else item
            for item in obj
        ]
    else:
        return data
    return (json.dumps(filtered, ensure_ascii=False) + "\n").encode("utf-8")


WAIT_BROWSER_HELP = "Browser wait: domcontentloaded, load, networkidle0, networkidle2"

# Extra seconds added to ScrapingBee --timeout (ms) for aiohttp client timeout (send/receive).
CLIENT_TIMEOUT_BUFFER_SECONDS = 30
DEFAULT_CLIENT_TIMEOUT_SECONDS = 150

DEVICE_DESKTOP_MOBILE = ["desktop", "mobile"]
DEVICE_DESKTOP_MOBILE_TABLET = ["desktop", "mobile", "tablet"]


def _validate_range(
    name: str,
    value: int | None,
    min_val: int,
    max_val: int,
    unit: str = "",
) -> None:
    """If value is not None, check min_val <= value <= max_val; on failure echo and raise SystemExit(1)."""
    if value is None:
        return
    if value < min_val or value > max_val:
        u = f" {unit}" if unit else ""
        click.echo(f"{name} must be between {min_val} and {max_val}{u}", err=True)
        raise SystemExit(1)


def _validate_page(value: int | None, name: str = "page") -> None:
    """Validate page number (>= 1)."""
    if value is not None and value < 1:
        click.echo(f"{name} must be at least 1", err=True)
        raise SystemExit(1)


def _validate_price_range(min_price: int | None, max_price: int | None) -> None:
    """Validate min_price/max_price: non-negative and min <= max."""
    if min_price is not None and min_price < 0:
        click.echo("min_price must be >= 0", err=True)
        raise SystemExit(1)
    if max_price is not None and max_price < 0:
        click.echo("max_price must be >= 0", err=True)
        raise SystemExit(1)
    if min_price is not None and max_price is not None and min_price > max_price:
        click.echo("min_price must be <= max_price", err=True)
        raise SystemExit(1)


def _validate_json_option(option_name: str, value: str | None) -> None:
    """If value is not None/empty, parse as JSON; on JSONDecodeError echo and raise SystemExit(1)."""
    if not value or not value.strip():
        return
    try:
        json.loads(value)
    except json.JSONDecodeError as e:
        click.echo(f"Invalid JSON in {option_name}: {e}", err=True)
        raise SystemExit(1)


def parse_bool(val: str | None) -> bool | None:
    """Parse a string to bool. None or empty -> None. Accepts true/1/yes -> True, false/0/no -> False.
    Raises ValueError for any other value so typos (e.g. treu) are not silently treated as False."""
    if not val or not str(val).strip():
        return None
    v = str(val).strip().lower()
    if v in ("true", "1", "yes"):
        return True
    if v in ("false", "0", "no"):
        return False
    raise ValueError(f"Invalid boolean '{val}'. Use true/false, 1/0, or yes/no.")


def build_scrape_kwargs(
    *,
    method: str = "GET",
    render_js: str | None = None,
    js_scenario: str | None = None,
    wait: int | None = None,
    wait_for: str | None = None,
    wait_browser: str | None = None,
    block_ads: str | None = None,
    block_resources: str | None = None,
    window_width: int | None = None,
    window_height: int | None = None,
    premium_proxy: str | None = None,
    stealth_proxy: str | None = None,
    country_code: str | None = None,
    own_proxy: str | None = None,
    forward_headers: str | None = None,
    forward_headers_pure: str | None = None,
    custom_headers: dict[str, str] | None = None,
    json_response: str | None = None,
    screenshot: str | None = None,
    screenshot_selector: str | None = None,
    screenshot_full_page: str | None = None,
    return_page_source: str | None = None,
    return_page_markdown: str | None = None,
    return_page_text: str | None = None,
    extract_rules: str | None = None,
    ai_query: str | None = None,
    ai_selector: str | None = None,
    ai_extract_rules: str | None = None,
    session_id: int | None = None,
    timeout: int | None = None,
    cookies: str | None = None,
    device: str | None = None,
    custom_google: str | None = None,
    transparent_status_code: str | None = None,
    body: str | None = None,
) -> dict[str, Any]:
    """Build kwargs for Client.scrape() from scrape command options.
    Single source of parse_bool for bool-like opts."""
    return {
        "method": method,
        "render_js": parse_bool(render_js),
        "js_scenario": js_scenario,
        "wait": wait,
        "wait_for": wait_for,
        "wait_browser": wait_browser,
        "block_ads": parse_bool(block_ads),
        "block_resources": parse_bool(block_resources),
        "window_width": window_width,
        "window_height": window_height,
        "premium_proxy": parse_bool(premium_proxy),
        "stealth_proxy": parse_bool(stealth_proxy),
        "country_code": country_code,
        "own_proxy": own_proxy,
        "forward_headers": parse_bool(forward_headers),
        "forward_headers_pure": parse_bool(forward_headers_pure),
        "custom_headers": custom_headers,
        "json_response": parse_bool(json_response),
        "screenshot": parse_bool(screenshot),
        "screenshot_selector": screenshot_selector,
        "screenshot_full_page": parse_bool(screenshot_full_page),
        "return_page_source": parse_bool(return_page_source),
        "return_page_markdown": parse_bool(return_page_markdown),
        "return_page_text": parse_bool(return_page_text),
        "extract_rules": extract_rules,
        "ai_query": ai_query,
        "ai_selector": ai_selector,
        "ai_extract_rules": ai_extract_rules,
        "session_id": session_id,
        "timeout": timeout,
        "cookies": cookies,
        "device": device,
        "custom_google": parse_bool(custom_google),
        "transparent_status_code": parse_bool(transparent_status_code),
        "body": body,
    }


def scrape_kwargs_to_api_params(kwargs: dict[str, Any]) -> dict[str, str]:
    """Convert build_scrape_kwargs output to ScrapingBee API params dict.
    Skips method, body, custom_headers. Output: str values only; omits None/empty."""
    skip_keys = frozenset(("method", "body", "custom_headers"))
    out: dict[str, str] = {}
    for k, v in kwargs.items():
        if k in skip_keys or v is None or v == "":
            continue
        if isinstance(v, bool):
            out[k] = "true" if v else "false"
        elif isinstance(v, int):
            out[k] = str(v)
        elif isinstance(v, str):
            out[k] = v
    return out


def check_api_response(data: bytes, status_code: int, err_prefix: str = "Error") -> None:
    """Exit with 1 on HTTP 4xx/5xx (per ScrapingBee docs).
    No special cases except scrape+transparent_status_code."""
    from .client import pretty_json

    if status_code >= 400:
        click.echo(f"{err_prefix}: HTTP {status_code}", err=True)
        try:
            click.echo(pretty_json(data), err=True)
        except Exception:
            click.echo(data.decode("utf-8", errors="replace"), err=True)
        raise SystemExit(1)


def norm_val(v: str | None) -> str | None:
    """Normalise a CLI choice value: hyphens → underscores for the API.

    CLI conventions use hyphens (e.g. ``most-recent``) but the ScrapingBee
    API expects underscores (``most_recent``).  Apply *only* to
    choice-constrained parameters — never to free-form text such as search
    queries, URLs, or JS scenarios.
    """
    return v.replace("-", "_") if v is not None else None


def chunk_text(text: str, size: int, overlap: int = 0) -> list[str]:
    """Split text into chunks of `size` chars with `overlap` chars of context.

    Args:
        text: The text to split.
        size: Maximum characters per chunk. If <= 0, returns [text].
        overlap: How many trailing chars of the previous chunk to repeat at
                 the start of the next one (must be < size).

    Returns:
        A list of non-empty string chunks.
    """
    if size <= 0:
        return [text]
    overlap = max(0, min(overlap, size - 1))
    step = size - overlap
    chunks = [text[i : i + size] for i in range(0, max(1, len(text)), step)]
    return [c for c in chunks if c]


def write_output(
    data: bytes,
    headers: dict,
    status_code: int,
    output_path: str | None,
    verbose: bool,
    *,
    extract_field: str | None = None,
    fields: str | None = None,
    command: str | None = None,
) -> None:
    """Write response data to file or stdout; optionally print verbose headers.

    When *extract_field* is set, extract values from JSON using a path expression
    (e.g. ``organic_results.url``) and output one value per line.
    When *fields* is set, filter JSON output to the specified comma-separated
    top-level keys (e.g. ``title,price,rating``).
    *extract_field* takes precedence over *fields*.
    When *command* is set and verbose mode is on, estimated credit cost is shown
    if the ``spb-cost`` header is absent (SERP endpoints omit this header).
    """
    if verbose:
        click.echo(f"HTTP Status: {status_code}", err=True)
        headers_lower = {k.lower(): (k, v) for k, v in headers.items()}
        spb_cost_present = False
        for key, label in [
            ("spb-cost", "Credit Cost"),
            ("spb-resolved-url", "Resolved URL"),
            ("spb-initial-status-code", "Initial Status Code"),
        ]:
            if key in headers_lower:
                _, val = headers_lower[key]
                if val:
                    click.echo(f"{label}: {val}", err=True)
                    if key == "spb-cost":
                        spb_cost_present = True
        if not spb_cost_present and command:
            from scrapingbee_cli.credits import ESTIMATED_CREDITS

            if command in ESTIMATED_CREDITS:
                click.echo(f"Credit Cost (estimated): {ESTIMATED_CREDITS[command]}", err=True)
        click.echo("---", err=True)
    if extract_field:
        data = _extract_field_values(data, extract_field)
    elif fields:
        data = _filter_fields(data, fields)
    if output_path:
        with open(output_path, "wb") as f:
            f.write(data)
    else:
        sys.stdout.buffer.write(data)
        # Only add a trailing newline for text-like content; binary data (PNG, PDF, etc.)
        # must not have extra bytes appended.
        if data and not data.endswith(b"\n"):
            is_text = data[:1] in (b"{", b"[", b"<", b"#") or b"\x00" not in data[:512]
            if is_text:
                click.echo()
