"""Shared CLI helpers and constants used by multiple commands."""

from __future__ import annotations

import json
import sys
from typing import Any

import click


class NormalizedChoice(click.Choice):
    """Choice type that accepts both hyphens and underscores.

    Automatically converts underscores to hyphens before validation,
    allowing users to use either format interchangeably.
    Example: both --sort-by price-low and --sort-by price_low work.
    """

    def convert(self, value: str, param: Any, ctx: Any) -> str:
        """Convert underscores to hyphens before validation."""
        if value is not None:
            normalized = value.replace("_", "-")
        else:
            normalized = value
        return super().convert(normalized, param, ctx)


def _output_options(f: Any) -> Any:
    """Output + Retry options (for commands without batch support)."""
    f = click.option(
        "--output-file",
        "output_file",
        type=click.Path(),
        default=None,
        help="Write output to file instead of stdout.",
    )(f)
    f = click.option(
        "--verbose", is_flag=True, default=False, help="Show response headers and status code."
    )(f)
    f = click.option(
        "--extract-field",
        "extract_field",
        type=str,
        default=None,
        help="Extract values from JSON using dot-path (e.g. organic_results.url).",
    )(f)
    f = click.option(
        "--fields", type=str, default=None, help="Comma-separated top-level JSON keys to include."
    )(f)
    f = click.option("--retries", type=int, default=3, help="Retry on errors (default: 3).")(f)
    f = click.option(
        "--backoff", type=float, default=2.0, help="Retry backoff multiplier (default: 2.0)."
    )(f)
    return f


def _batch_options(f: Any) -> Any:
    """Output + Batch + Retry options (for commands with batch support)."""
    f = click.option(
        "--output-file",
        "output_file",
        type=click.Path(),
        default=None,
        help="Write output to file instead of stdout.",
    )(f)
    f = click.option(
        "--verbose", is_flag=True, default=False, help="Show response headers and status code."
    )(f)
    f = click.option(
        "--extract-field",
        "extract_field",
        type=str,
        default=None,
        help="Extract values from JSON using dot-path.",
    )(f)
    f = click.option(
        "--fields", type=str, default=None, help="Comma-separated top-level JSON keys to include."
    )(f)
    f = click.option(
        "--input-file",
        "input_file",
        type=str,
        default=None,
        help="Batch: one item per line. Use - for stdin.",
    )(f)
    f = click.option(
        "--input-column",
        "input_column",
        type=str,
        default=None,
        help="CSV input: column name or 0-based index.",
    )(f)
    f = click.option("--output-dir", "output_dir", default=None, help="Batch output folder.")(f)
    f = click.option(
        "--output-format",
        "output_format",
        type=click.Choice(["files", "csv", "ndjson"], case_sensitive=False),
        default="files",
        help="Batch: output format (files, csv, or ndjson).",
    )(f)
    f = click.option(
        "--concurrency",
        type=int,
        default=0,
        help="Batch: max concurrent requests (0 = auto from plan).",
    )(f)
    f = click.option(
        "--deduplicate",
        is_flag=True,
        default=False,
        help="Batch: normalize URLs and remove duplicates from input.",
    )(f)
    f = click.option(
        "--sample",
        type=int,
        default=0,
        help="Batch: process only N random items from input (0 = all).",
    )(f)
    f = click.option(
        "--post-process",
        "post_process",
        type=str,
        default=None,
        help="[Advanced] Batch: pipe each result through a shell command (e.g. 'jq .title'). Requires unsafe mode.",
    )(f)
    f = click.option(
        "--update-csv",
        "update_csv",
        is_flag=True,
        default=False,
        help="Batch: fetch fresh data and update the input CSV in-place.",
    )(f)
    f = click.option(
        "--resume",
        is_flag=True,
        default=False,
        help="Batch: skip items already saved in --output-dir.",
    )(f)
    f = click.option(
        "--no-progress",
        "no_progress",
        is_flag=True,
        default=False,
        help="Batch: suppress progress display.",
    )(f)
    f = click.option(
        "--on-complete",
        "on_complete",
        type=str,
        default=None,
        help="[Advanced] Batch: shell command to run after completion. Requires unsafe mode.",
    )(f)
    f = click.option("--retries", type=int, default=3, help="Retry on errors (default: 3).")(f)
    f = click.option(
        "--backoff", type=float, default=2.0, help="Retry backoff multiplier (default: 2.0)."
    )(f)
    return f


def store_common_options(obj: dict, **kwargs: Any) -> None:
    """Store decorator option values into the obj dict."""
    obj["output_file"] = kwargs.get("output_file")
    obj["verbose"] = kwargs.get("verbose", False)
    obj["extract_field"] = kwargs.get("extract_field")
    obj["fields"] = kwargs.get("fields")
    obj["input_file"] = kwargs.get("input_file")
    obj["input_column"] = kwargs.get("input_column")
    obj["output_dir"] = kwargs.get("output_dir") or ""
    obj["output_format"] = kwargs.get("output_format", "files")
    obj["concurrency"] = kwargs.get("concurrency") or 0
    obj["deduplicate"] = kwargs.get("deduplicate", False)
    obj["sample"] = kwargs.get("sample", 0)
    obj["post_process"] = kwargs.get("post_process")
    obj["update_csv"] = kwargs.get("update_csv", False)
    obj["resume"] = kwargs.get("resume", False)
    obj["progress"] = not kwargs.get("no_progress", False)
    obj["on_complete"] = kwargs.get("on_complete")
    obj["retries"] = kwargs.get("retries") if kwargs.get("retries") is not None else 3
    obj["backoff"] = kwargs.get("backoff") if kwargs.get("backoff") is not None else 2.0


def _resolve_dotpath(obj: Any, keys: list[str]) -> Any:
    """Walk *obj* using *keys* (dot-path segments).

    - When a segment hits a **list**, the remaining path is applied to every
      dict item in that list and the results are collected into a flat list.
    - When a segment hits a **dict**, traversal continues into the nested dict.
    - Returns ``None`` if the path cannot be resolved.
    """
    cur: Any = obj
    for i, key in enumerate(keys):
        if isinstance(cur, dict):
            cur = cur.get(key)
            if cur is None:
                return None
        elif isinstance(cur, list):
            # Remaining keys need to be applied to each item in the list.
            rest = keys[i:]
            collected: list[Any] = []
            for item in cur:
                v = _resolve_dotpath(item, rest)
                if v is None:
                    continue
                if isinstance(v, list):
                    collected.extend(v)
                else:
                    collected.append(v)
            return collected if collected else None
        else:
            return None
    return cur


def _collect_dotpaths(obj: Any, prefix: str = "", max_depth: int = 4) -> list[str]:
    """Recursively collect all valid dot-paths from a JSON object.

    For arrays, peeks into the first element. Caps at *max_depth* to
    avoid huge output on deeply nested structures.
    """
    if max_depth <= 0:
        return []
    paths: list[str] = []
    if isinstance(obj, dict):
        for key in obj.keys():
            full = f"{prefix}.{key}" if prefix else key
            paths.append(full)
            paths.extend(_collect_dotpaths(obj[key], full, max_depth - 1))
    elif isinstance(obj, list) and obj:
        # Peek into first element to show available sub-paths
        first = obj[0] if isinstance(obj[0], dict) else None
        if first:
            paths.extend(_collect_dotpaths(first, prefix, max_depth - 1))
    return paths


def _extract_field_values(data: bytes, path: str) -> bytes:
    """Extract values from JSON data using a dot-path expression.

    Supports arbitrary nesting depth: ``key``, ``key.subkey``,
    ``key.subkey.deeper``, etc.  When a segment resolves to a list, the
    remaining path is applied to every dict item in that list (one output
    value per item).

    Returns newline-separated UTF-8 bytes, suitable for use as ``--input-file``.
    Returns *data* unchanged if parsing fails or the path is not found.
    """
    try:
        obj = json.loads(data.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return data

    keys = path.split(".")
    result = _resolve_dotpath(obj, keys)

    if result is None:
        paths = _collect_dotpaths(obj)
        hint = ""
        if paths:
            hint = "\n  Available paths:\n    " + "\n    ".join(paths)
        click.echo(
            f"Warning: --extract-field '{path}' did not match any data.{hint}",
            err=True,
        )
        return b""
    if isinstance(result, list):
        values = [str(v) for v in result if v is not None]
    else:
        values = [str(result)]

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
    scraping_config: str | None = None,
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
        "scraping_config": scraping_config,
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


def _is_blocked(status_code: int, headers: dict) -> bool:
    """Check if the **target site** blocked the request (403/429).

    The ScrapingBee API uses its own status codes (e.g. API 429 = plan
    concurrency limit, not target blocking).  The target's real status is
    always in the ``spb-initial-status-code`` response header, regardless
    of ``--transparent-status-code``.
    """
    for k, v in headers.items():
        if k.lower() == "spb-initial-status-code":
            try:
                return int(v) in (403, 429)
            except (ValueError, TypeError):
                pass
    return False


_PROXY_TIERS: list[tuple[str, dict[str, bool]]] = [
    ("premium", {"premium_proxy": True}),
    ("stealth", {"stealth_proxy": True}),
]


async def scrape_with_escalation(
    client: Any,
    url: str,
    scrape_kwargs: dict[str, Any],
    *,
    verbose: bool = False,
) -> tuple[bytes, dict, int]:
    """Call ``client.scrape`` with automatic proxy tier escalation on 403/429.

    Tries the request as-is first.  If the response indicates blocking, retries
    with ``premium_proxy``, then ``stealth_proxy``.  Already-set proxy flags
    are respected: if the user passed ``--premium-proxy``, escalation starts
    from stealth.

    Returns the final ``(data, headers, status_code)`` tuple.
    """
    data, headers, status_code = await client.scrape(url, **scrape_kwargs)
    if not _is_blocked(status_code, headers):
        return data, headers, status_code

    for tier_name, tier_overrides in _PROXY_TIERS:
        # Skip tiers the user already set.
        already = any(scrape_kwargs.get(k) for k in tier_overrides)
        if already:
            continue
        click.echo(f"[escalate-proxy] {url}: blocked, retrying with {tier_name} proxy", err=True)
        escalated = {**scrape_kwargs, **tier_overrides}
        data, headers, status_code = await client.scrape(url, **escalated)
        if verbose:
            cost = None
            for k, v in headers.items():
                if k.lower() == "spb-cost":
                    cost = v
                    break
            cost_str = f" ({cost} credits)" if cost else ""
            click.echo(f"[escalate-proxy] {tier_name} → HTTP {status_code}{cost_str}", err=True)
        if not _is_blocked(status_code, headers):
            return data, headers, status_code

    return data, headers, status_code


def ensure_url_scheme(url: str) -> str:
    """Prepend https:// if the URL has no scheme (like curl/httpie do)."""
    if url and not url.startswith(("http://", "https://", "ftp://")):
        return "https://" + url
    return url


def prepare_batch_inputs(inputs: list[str], obj: dict) -> list[str]:
    """Apply --deduplicate and --sample to batch inputs."""
    from .batch import deduplicate_inputs, sample_inputs

    if obj.get("deduplicate"):
        inputs, removed = deduplicate_inputs(inputs)
        if removed:
            click.echo(
                f"Deduplicated: removed {removed} duplicate(s), {len(inputs)} unique", err=True
            )
    sample_n = obj.get("sample", 0)
    if sample_n > 0:
        inputs = sample_inputs(inputs, sample_n)
        click.echo(f"Sampled {len(inputs)} items from input", err=True)
    return inputs


def run_on_complete(
    cmd: str | None,
    *,
    output_dir: str = "",
    succeeded: int = 0,
    failed: int = 0,
) -> None:
    """Run the ``--on-complete`` shell command if set.

    Injects ``SCRAPINGBEE_OUTPUT_DIR``, ``SCRAPINGBEE_SUCCEEDED``, and
    ``SCRAPINGBEE_FAILED`` environment variables.
    """
    if not cmd:
        return
    import os
    import subprocess

    from .audit import log_exec
    from .exec_gate import require_exec

    require_exec("--on-complete", cmd)
    log_exec("on-complete", cmd, output_dir=output_dir)
    click.echo(f"⚠ Executing: {cmd.split()[0] if cmd.split() else cmd} (whitelisted)", err=True)

    env = os.environ.copy()
    env["SCRAPINGBEE_OUTPUT_DIR"] = output_dir
    env["SCRAPINGBEE_SUCCEEDED"] = str(succeeded)
    env["SCRAPINGBEE_FAILED"] = str(failed)
    result = subprocess.run(cmd, shell=True, env=env)  # noqa: S602
    if result.returncode != 0:
        click.echo(f"[on-complete] Exit code: {result.returncode}", err=True)


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
    credit_cost: int | None = None,
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
        if not spb_cost_present:
            if credit_cost is not None:
                click.echo(f"Credit Cost: {credit_cost}", err=True)
            elif command:
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
