"""Smart extraction — auto-detect format, convert to dict, apply path language.

Supports JSON, HTML, XML, CSV, NDJSON, YAML, Markdown, and plain text.
All formats are converted to Python dicts/lists, then the path language
from cli_utils is applied.
"""

from __future__ import annotations

import csv
import io
import json
import re
from typing import Any

import click

from .cli_utils import (
    _collect_dotpaths,
    _parse_field_blocks,
    resolve_expression,
)

# ── Format converters ─────────────────────────────────────────────────────────


def _element_to_dict(el: Any) -> Any:
    """Convert an lxml element to a dict.

    - Attributes become keys (``href``, ``class``, ``id``, etc.)
    - Child elements become nested dicts (or lists if repeated)
    - Text content is stored under the ``text`` key
    - If an element has only text (no attrs, no children), returns the string
    """
    d: dict[str, Any] = {}

    # Attributes
    for k, v in el.attrib.items():
        d[k] = v

    # Text content
    text = el.text.strip() if el.text else ""

    # Children
    for child in el:
        tag = child.tag
        if not isinstance(tag, str):
            continue  # skip comments, processing instructions
        child_val = _element_to_dict(child)
        if tag in d:
            if not isinstance(d[tag], list):
                d[tag] = [d[tag]]
            d[tag].append(child_val)
        else:
            d[tag] = child_val
        # Tail text (text after a child element, before the next sibling)
        if child.tail and child.tail.strip():
            d.setdefault("tail_text", []).append(child.tail.strip())

    if text:
        d["text"] = text

    # Simplify: element with only text → just the string
    if not d and text:
        return text
    if len(d) == 1 and "text" in d:
        return text

    return d if d else ""


def _html_to_dict(data: bytes) -> dict | None:
    """Parse HTML bytes into a dict tree using lxml."""
    try:
        from lxml import html

        tree = html.fromstring(data)
        return _element_to_dict(tree)
    except Exception:
        return None


def _xml_to_dict(data: bytes) -> dict | None:
    """Parse XML bytes into a dict tree using lxml."""
    try:
        from lxml import etree  # type: ignore[attr-defined]

        tree = etree.fromstring(data)
        return _element_to_dict(tree)
    except Exception:
        return None


def _csv_to_list(data: bytes) -> list[dict] | None:
    """Parse CSV bytes into a list of dicts (one per row).

    Validates that the data looks like real CSV: short column names,
    consistent column count, and at least 2 rows.
    """
    try:
        text = data.decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        if len(rows) < 1:
            return None
        # Reject if column names look like prose (too long → not a real header)
        headers = list(rows[0].keys())
        if any(len(h) > 60 for h in headers):
            return None
        # Reject if too few columns (single-column "CSV" is just text)
        if len(headers) < 2:
            return None
        return rows
    except Exception:
        return None


def _ndjson_to_list(data: bytes) -> list | None:
    """Parse NDJSON (one JSON object per line) into a list."""
    try:
        text = data.decode("utf-8", errors="replace")
        lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
        if len(lines) < 2:
            return None  # single line = regular JSON, not NDJSON
        items = [json.loads(line) for line in lines]
        return items
    except (json.JSONDecodeError, ValueError):
        return None


def _txt_to_list(data: bytes) -> list[str]:
    """Convert plain text to a list of lines."""
    return data.decode("utf-8", errors="replace").splitlines()


def _parse_md_table(lines: list[str]) -> list[dict[str, str]] | None:
    """Parse markdown table lines into a list of dicts.

    Expects: header row, separator row (``|---|---|``), then data rows.
    Returns None if the lines don't form a valid table.
    """
    if len(lines) < 3:
        return None
    # Header row
    headers = [h.strip() for h in lines[0].strip("|").split("|") if h.strip()]
    if not headers:
        return None
    # Verify separator row (all cells are dashes/colons)
    sep_cells = [c.strip() for c in lines[1].strip("|").split("|")]
    if not all(re.match(r"^:?-+:?$", c) for c in sep_cells if c.strip()):
        return None
    # Data rows
    rows: list[dict[str, str]] = []
    for line in lines[2:]:
        cells = [c.strip() for c in line.strip("|").split("|")]
        row = {}
        for j, header in enumerate(headers):
            row[header] = cells[j] if j < len(cells) else ""
        rows.append(row)
    return rows


def _markdown_to_dict(data: bytes) -> dict | None:
    """Parse Markdown into a heading-based dict tree.

    Headings (``#``, ``##``, etc.) create nested dict keys. Text between
    headings is stored under the ``text`` key. Markdown tables are parsed
    into lists of dicts under the ``tables`` key.

    Example::

        # API Reference          →  {"API Reference": {
        Some intro text                "text": "Some intro text",
                                       "Authentication": {
        ## Authentication                  "text": "Use bearer tokens"
        Use bearer tokens              },
                                       "Endpoints": {
        ## Endpoints                       "tables": [
        | path  | method |                     {"path": "/get", "method": "GET"}
        |-------|--------|                 ]
        | /get  | GET    |             }
                                     }}
    """
    text = data.decode("utf-8", errors="replace")
    lines = text.split("\n")

    # Check for any kind of heading: ATX (# ...) or setext (=== / --- underlines)
    has_atx = any(re.match(r"^#{1,6}\s", line) for line in lines[:100])
    has_setext = any(re.match(r"^[=-]{3,}\s*$", line) for line in lines[:100])
    if not has_atx and not has_setext:
        return None  # No headings found — not Markdown

    root: dict[str, Any] = {}
    # Stack of (heading_level, dict_ref) — level 0 is root
    stack: list[tuple[int, dict[str, Any]]] = [(0, root)]
    text_buf: list[str] = []
    table_buf: list[str] = []

    def _flush_text() -> None:
        """Flush accumulated text lines to the current section."""
        nonlocal text_buf
        content = "\n".join(text_buf).strip()
        if content:
            section = stack[-1][1]
            if "text" in section:
                section["text"] += "\n" + content
            else:
                section["text"] = content
        text_buf = []

    def _flush_table() -> None:
        """Flush accumulated table lines to the current section."""
        nonlocal table_buf
        if not table_buf:
            return
        parsed = _parse_md_table(table_buf)
        if parsed:
            section = stack[-1][1]
            section.setdefault("tables", []).extend(parsed)
        table_buf = []

    def _add_heading(level: int, title: str) -> None:
        """Add a heading to the tree at the given level."""
        _flush_text()
        _flush_table()
        while len(stack) > 1 and stack[-1][0] >= level:
            stack.pop()
        new_section: dict[str, Any] = {}
        parent = stack[-1][1]
        if title in parent:
            n = 2
            while f"{title} ({n})" in parent:
                n += 1
            title = f"{title} ({n})"
        parent[title] = new_section
        stack.append((level, new_section))

    i = 0
    while i < len(lines):
        line = lines[i]

        # Check for setext heading: next line is === (h1) or --- (h2)
        if i + 1 < len(lines) and line.strip():
            next_line = lines[i + 1]
            if re.match(r"^={3,}\s*$", next_line):
                _add_heading(1, line.strip())
                i += 2  # skip underline
                continue
            if re.match(r"^-{3,}\s*$", next_line) and not line.strip().startswith("|"):
                _add_heading(2, line.strip())
                i += 2
                continue

        # Check for ATX heading: # ...
        heading_match = re.match(r"^(#{1,6})\s+(.*)", line)
        if heading_match:
            _add_heading(len(heading_match.group(1)), heading_match.group(2).strip())
            i += 1
            continue

        # Check for table row (starts with |)
        if line.strip().startswith("|") and "|" in line.strip()[1:]:
            _flush_text()
            table_buf.append(line)
            i += 1
            continue

        # If we were in a table and this line isn't a table row, flush
        if table_buf:
            _flush_table()

        # Regular text line
        text_buf.append(line)
        i += 1

    # Flush remaining
    _flush_text()
    _flush_table()

    return root if root else None


# ── Auto-detection ────────────────────────────────────────────────────────────

_MD_ATX_RE = re.compile(r"^#{1,6}\s", re.MULTILINE)
# Only === for setext detection (--- is too ambiguous — HR, YAML front matter, separators)
_MD_SETEXT_RE = re.compile(r"^.+\n={3,}\s*$", re.MULTILINE)


def _auto_parse(data: bytes) -> Any:
    """Auto-detect the format of *data* and convert to a Python dict/list.

    Detection order:
    1. JSON (starts with ``{`` or ``[``)
    2. NDJSON (multiple ``{...}`` lines — only if JSON parse fails)
    3. HTML/XML (starts with ``<``)
    4. CSV (contains commas and newlines, first line looks like a header)
    5. Markdown (contains ``# `` headings)
    6. Plain text (fallback)
    """
    stripped = data.lstrip()
    if not stripped:
        return None

    # JSON or NDJSON
    if stripped.startswith(b"{") or stripped.startswith(b"["):
        decoded = data.decode("utf-8", errors="replace")
        try:
            return json.loads(decoded)
        except json.JSONDecodeError:
            pass
        # Maybe NDJSON (multiple JSON lines)
        result = _ndjson_to_list(data)
        if result:
            return result

    # HTML or XML
    if stripped.startswith(b"<"):
        header = stripped[:200].lower()
        if b"<?xml" in header or b"<rss" in header or b"<feed" in header:
            result = _xml_to_dict(data)
            if result is not None:
                return result
        result = _html_to_dict(data)
        if result is not None:
            return result

    # CSV (has commas and multiple lines, not starting with < or {)
    if b"," in stripped and b"\n" in stripped:
        result = _csv_to_list(data)
        if result is not None:
            return result

    # Markdown (has # headings or === / --- underlines)
    decoded_for_check = stripped[:1000].decode("utf-8", errors="replace")
    if _MD_ATX_RE.search(decoded_for_check) or _MD_SETEXT_RE.search(decoded_for_check):
        result = _markdown_to_dict(data)
        if result is not None:
            return result

    # Plain text fallback — list of lines
    return _txt_to_list(data)


# ── Smart extract ─────────────────────────────────────────────────────────────


def _serialize_value(v: Any) -> str:
    """Serialize a value for raw output (one per line)."""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def smart_extract(data: bytes, expression: str) -> bytes:
    """Auto-detect format, convert to dict, and apply the path language.

    Three modes, auto-detected:

    **JSON schema** (production mode — same format as --extract-rules)::

        smart_extract(data, '{"email": "...a[href=*mailto*].text", "links": "...href"}')

    **Named blocks** (quick shorthand)::

        smart_extract(data, '{email:...href},{links:...href}')

    **Single path** (raw output, one value per line)::

        smart_extract(data, '...href')

    Auto-detects input format: JSON, HTML, XML, CSV, NDJSON, Markdown, text.
    """
    obj = _auto_parse(data)
    if obj is None:
        click.echo("Warning: could not parse response data.", err=True)
        return data

    # Mode 1: JSON schema — {"name": "path", ...}
    if expression.strip().startswith("{"):
        try:
            schema = json.loads(expression)
            if isinstance(schema, dict):
                return _smart_extract_schema(obj, schema)
        except (json.JSONDecodeError, ValueError):
            pass
        # Not valid JSON — Mode 2: {name:path} block syntax
        return _smart_extract_structured(obj, expression)

    # Mode 3: raw path / OR / AND expression
    return _smart_extract_raw(obj, expression)


def _smart_extract_schema(obj: Any, schema: dict[str, Any]) -> bytes:
    """JSON schema mode: keys are output names, values are path expressions.

    Mirrors ``--extract-rules`` and ``--ai-extract-rules`` format::

        {"email": "...a[href=*mailto*].text", "phone": "...*phone*"}
    """
    output: dict[str, Any] = {}
    for name, path_expr in schema.items():
        if not isinstance(path_expr, str):
            click.echo(
                f"Warning: --smart-extract field '{name}' must be a string path, "
                f"got {type(path_expr).__name__}. Skipping.",
                err=True,
            )
            continue
        result = resolve_expression(obj, path_expr)
        if result is not None:
            output[name] = result

    if not output:
        hints = _collect_dotpaths(obj)
        hint = ""
        if hints:
            hint = "\n  Available paths:\n    " + "\n    ".join(hints[:30])
        click.echo(
            f"Warning: --smart-extract schema did not match any data.{hint}",
            err=True,
        )
        return b""

    return (json.dumps(output, ensure_ascii=False) + "\n").encode("utf-8")


def _smart_extract_raw(obj: Any, expression: str) -> bytes:
    """Single expression → raw values, one per line.

    Supports ``|`` OR, ``&`` AND, and ``=`` value filter.
    """
    result = resolve_expression(obj, expression)

    if result is None:
        hints = _collect_dotpaths(obj)
        hint = ""
        if hints:
            hint = "\n  Available paths:\n    " + "\n    ".join(hints[:30])
        click.echo(
            f"Warning: --smart-extract '{expression}' did not match any data.{hint}",
            err=True,
        )
        return b""

    if isinstance(result, list):
        values = [_serialize_value(v) for v in result if v is not None]
    else:
        values = [_serialize_value(result)]

    return ("\n".join(values) + "\n").encode("utf-8") if values else b""


def _smart_extract_structured(obj: Any, expression: str) -> bytes:
    """Named blocks → structured JSON output.

    Each ``{name:path}`` block supports the full expression syntax
    including ``=`` value filter.
    """
    blocks = _parse_field_blocks(expression)
    if not blocks:
        return b""

    output: dict[str, Any] = {}
    for name, path_str in blocks:
        val = resolve_expression(obj, path_str)
        if val is not None:
            output[name] = val

    if not output:
        hints = _collect_dotpaths(obj)
        hint = ""
        if hints:
            hint = "\n  Available paths:\n    " + "\n    ".join(hints[:30])
        paths_tried = ", ".join(p for _, p in blocks)
        click.echo(
            f"Warning: --smart-extract '{paths_tried}' did not match any data.{hint}",
            err=True,
        )
        return b""

    return (json.dumps(output, ensure_ascii=False) + "\n").encode("utf-8")
