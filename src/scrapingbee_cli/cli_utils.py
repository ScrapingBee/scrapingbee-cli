"""Shared CLI helpers and constants used by multiple commands."""

from __future__ import annotations

import fnmatch
import json
import re
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
        "--smart-extract",
        "smart_extract",
        type=str,
        default=None,
        help="Extract data using path language. Auto-detects JSON/HTML/XML/CSV.",
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
        "--smart-extract",
        "smart_extract",
        type=str,
        default=None,
        help="Extract data using path language. Auto-detects JSON/HTML/XML/CSV.",
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
        type=click.Choice(["csv", "ndjson"], case_sensitive=False),
        default=None,
        help="Batch: stream all results to a single file (csv or ndjson). Default: individual files in --output-dir.",
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
        help="Batch: normalize URLs and remove duplicates from input. Runs before --sample.",
    )(f)
    f = click.option(
        "--sample",
        type=int,
        default=0,
        help="Batch: process only N random items from input (0 = all). Runs after --deduplicate.",
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
    f = click.option(
        "--overwrite", is_flag=True, default=False, help="Overwrite output file without prompting."
    )(f)
    return f


def confirm_overwrite(path: str | None, overwrite: bool = False) -> None:
    """If path exists, prompt for confirmation unless --overwrite is set."""
    if not path:
        return
    from pathlib import Path

    if Path(path).exists() and not overwrite:
        if not click.confirm(f"'{path}' already exists. Overwrite?"):
            click.echo("Cancelled.", err=True)
            raise SystemExit(0)


def store_common_options(obj: dict, **kwargs: Any) -> None:
    """Store decorator option values into the obj dict."""
    obj["output_file"] = kwargs.get("output_file")
    obj["verbose"] = kwargs.get("verbose", False)
    obj["smart_extract"] = kwargs.get("smart_extract")
    obj["extract_field"] = kwargs.get("extract_field")
    obj["fields"] = kwargs.get("fields")
    if obj["extract_field"] and not obj["smart_extract"]:
        click.echo(
            "Note: --extract-field is deprecated and will be removed in v2.0.0. "
            "Use --smart-extract instead (same syntax, plus auto-format detection).",
            err=True,
        )
    if obj["fields"] and not obj["smart_extract"]:
        click.echo(
            "Note: --fields is deprecated and will be removed in v2.0.0. "
            "Use --smart-extract with '{name:path}' syntax instead.",
            err=True,
        )
    obj["input_file"] = kwargs.get("input_file")
    obj["input_column"] = kwargs.get("input_column")
    obj["output_dir"] = kwargs.get("output_dir") or ""
    obj["output_format"] = kwargs.get("output_format")  # None = individual files
    raw_concurrency = kwargs.get("concurrency") or 0
    if raw_concurrency < 0:
        click.echo(
            f"Invalid --concurrency value: {raw_concurrency}. Must be 0 (auto) or a positive number.",
            err=True,
        )
        raise SystemExit(1)
    obj["concurrency"] = raw_concurrency
    obj["deduplicate"] = kwargs.get("deduplicate", False)
    obj["sample"] = kwargs.get("sample", 0)
    obj["post_process"] = kwargs.get("post_process")
    obj["update_csv"] = kwargs.get("update_csv", False)
    obj["resume"] = kwargs.get("resume", False)
    obj["progress"] = not kwargs.get("no_progress", False)
    obj["on_complete"] = kwargs.get("on_complete")
    obj["overwrite"] = kwargs.get("overwrite", False)
    obj["retries"] = kwargs.get("retries") if kwargs.get("retries") is not None else 3
    obj["backoff"] = kwargs.get("backoff") if kwargs.get("backoff") is not None else 2.0

    # Validate flag combinations
    output_format = obj["output_format"]
    has_input = bool(obj.get("input_file"))
    has_output_file = bool(obj.get("output_file"))
    has_output_dir = bool(obj.get("output_dir"))

    # Check if output file already exists (skip for --update-csv which intentionally overwrites)
    if has_output_file and not obj.get("update_csv"):
        confirm_overwrite(obj["output_file"], obj.get("overwrite", False))

    # Mutual exclusion: --output-file and --output-dir
    if has_output_file and has_output_dir:
        click.echo(
            "Cannot use both --output-file and --output-dir. "
            "Use --output-file for single-file output (csv/ndjson), "
            "or --output-dir for individual files.",
            err=True,
        )
        raise SystemExit(1)

    if has_input:
        if output_format in ("csv", "ndjson"):
            # Single-file formats: use --output-file, not --output-dir
            if has_output_dir:
                click.echo(
                    f"Cannot use --output-dir with --output-format {output_format}. "
                    f"Use --output-file to specify a file path, or omit for stdout.",
                    err=True,
                )
                raise SystemExit(1)
        else:
            # Individual files mode: use --output-dir, not --output-file
            if has_output_file:
                click.echo(
                    "Cannot use --output-file in batch mode without --output-format. "
                    "Use --output-dir for batch output, or use `scrapingbee export` to merge results.",
                    err=True,
                )
                raise SystemExit(1)
        if obj.get("update_csv"):
            if output_format == "csv":
                click.echo(
                    "Cannot use --update-csv with --output-format csv. "
                    "--update-csv already produces CSV by updating the input file.",
                    err=True,
                )
                raise SystemExit(1)
            if not str(obj["input_file"]).lower().endswith(".csv"):
                click.echo(
                    "--update-csv requires a CSV input file (ending in .csv).",
                    err=True,
                )
                raise SystemExit(1)
        if obj.get("resume") and output_format in ("csv", "ndjson"):
            click.echo(
                f"Cannot use --resume with --output-format {output_format}. "
                "--resume only works with individual files mode (no --output-format).",
                err=True,
            )
            raise SystemExit(1)
        if obj.get("extract_field") and output_format in ("csv", "ndjson"):
            click.echo(
                f"Cannot use --extract-field with --output-format {output_format}. "
                "--extract-field works with individual files mode (no --output-format). "
                "Use --fields to filter nested fields in csv/ndjson output.",
                err=True,
            )
            raise SystemExit(1)
        if obj.get("on_complete") and output_format and not has_output_file:
            click.echo(
                f"Cannot use --on-complete with --output-format {output_format} without --output-file. "
                "The on-complete script needs a file path to reference.",
                err=True,
            )
            raise SystemExit(1)
    else:
        # Single-URL mode: reject batch-only flags
        batch_only = []
        if obj.get("update_csv"):
            batch_only.append("--update-csv")
        if obj.get("resume"):
            batch_only.append("--resume")
        if has_output_dir:
            batch_only.append("--output-dir")
        if obj.get("concurrency"):
            batch_only.append("--concurrency")
        if obj.get("deduplicate"):
            batch_only.append("--deduplicate")
        if obj.get("sample"):
            batch_only.append("--sample")
        if obj.get("input_column"):
            batch_only.append("--input-column")
        if obj.get("on_complete"):
            batch_only.append("--on-complete")
        if output_format:
            batch_only.append("--output-format")
        if obj.get("post_process"):
            batch_only.append("--post-process")
        if batch_only:
            import shlex
            import sys

            click.echo(
                f"Cannot use {', '.join(batch_only)} without --input-file (batch mode only).",
                err=True,
            )
            # Reconstruct a suggested batch command from argv
            _bool_flags = {
                "--deduplicate",
                "--no-progress",
                "--resume",
                "--update-csv",
                "--verbose",
                "--overwrite",
                "--escalate-proxy",
            }
            kept: list[str] = []
            argv_rest = sys.argv[2:]  # after 'scrapingbee <command>'
            i = 0
            while i < len(argv_rest):
                arg = argv_rest[i]
                if arg.startswith("-"):
                    kept.append(arg)
                    if (
                        arg not in _bool_flags
                        and i + 1 < len(argv_rest)
                        and not argv_rest[i + 1].startswith("-")
                    ):
                        i += 1
                        kept.append(argv_rest[i])
                # else: positional (URL, query, ASIN…) — drop it
                i += 1
            cmd_name = sys.argv[1] if len(sys.argv) > 1 else "scrape"
            suggestion = " ".join(
                ["scrapingbee", shlex.quote(cmd_name), "--input-file", "urls.txt"]
                + [shlex.quote(a) for a in kept]
            )
            click.echo(f"Use --input-file to run in batch mode:\n  {suggestion}", err=True)
            if "--resume" in batch_only:
                click.echo(
                    "To discover incomplete batches in the current directory:\n"
                    "  scrapingbee --resume",
                    err=True,
                )
            raise SystemExit(1)


def _parse_path(path: str) -> list[tuple[str, Any]]:
    """Parse a path expression into typed segments.

    Syntax
    ------
    ``.key``           literal key navigation (maps over lists)
    ``(any chars)``    escaped literal key (for keys with dots, spaces, etc.)
    ``[0]``, ``[-1]``  index into array or dict by position
    ``[0, 3, 7]``      multi-index (cherry-pick specific items)
    ``[0:5]``          slice (contiguous range)
    ``[keys]``         dict keys as a list (maps over lists)
    ``[values]``       dict values as a list (maps over lists)
    ``...key``         recursive search — find key at any depth
    ``...(esc)``       recursive search with escaped key name

    Examples
    --------
    >>> _parse_path("xhr.body.paths")
    [("key", "xhr"), ("key", "body"), ("key", "paths")]
    >>> _parse_path("xhr[0].body.paths[keys]")
    [("key", "xhr"), ("index", 0), ("key", "body"), ("key", "paths"), ("keys", None)]
    >>> _parse_path("(a.b).c")
    [("key", "a.b"), ("key", "c")]
    >>> _parse_path("...summary")
    [("recurse", "summary")]
    >>> _parse_path("xhr.body.paths[0, 3, 7]")
    [("key", "xhr"), ("key", "body"), ("key", "paths"), ("multi_index", [0, 3, 7])]
    """
    segments: list[tuple[str, Any]] = []
    i = 0
    n = len(path)

    def _read_paren(start: int) -> tuple[str, int]:
        """Read from ``(`` to depth-matched ``)``, return (content, end_pos)."""
        depth = 1
        j = start + 1
        while j < n and depth > 0:
            if path[j] == "(":
                depth += 1
            elif path[j] == ")":
                depth -= 1
            j += 1
        return path[start + 1 : j - 1], j

    while i < n:
        # --- Recursive search: ...key~N or ...(escaped)~N ---
        if path[i : i + 3] == "...":
            i += 3
            if i < n and path[i] == "(":
                key, i = _read_paren(i)
            else:
                j = i
                while j < n and path[j] not in ".[(~":
                    j += 1
                key = path[i:j]
                i = j
            # Optional ~N context expansion suffix
            context = 0
            if i < n and path[i] == "~":
                i += 1
                j = i
                while j < n and path[j].isdigit():
                    j += 1
                context = int(path[i:j]) if j > i else 0
                i = j
            if key:
                segments.append(("recurse", (key, context)))

        # --- Dot separator ---
        elif path[i] == ".":
            i += 1

        # --- Escaped literal key: (any chars) ---
        elif path[i] == "(":
            key, i = _read_paren(i)
            segments.append(("key", key))

        # --- Bracket expression: [0], [0:5], [0,3,7], [keys], [values] ---
        elif path[i] == "[":
            try:
                j = path.index("]", i + 1)
            except ValueError:
                segments.append(("key", path[i:]))
                break
            inner = path[i + 1 : j].strip()
            if inner == "keys":
                segments.append(("keys", None))
            elif inner == "values":
                segments.append(("values", None))
            elif inner.startswith("!="):
                # Negated value filter: [!=pattern]
                segments.append(("filter_value_not", inner[2:]))
            elif inner.startswith("="):
                # Value filter: [=*pattern*]
                segments.append(("filter_value", inner[1:]))
            elif "!=" in inner and not inner.lstrip("-").isdigit():
                # Negated key filter: [key!=pattern]
                eq = inner.index("!=")
                segments.append(("filter_key_not", (inner[:eq].strip(), inner[eq + 2 :].strip())))
            elif "=" in inner and not inner.lstrip("-").isdigit():
                # Key filter: [key=*pattern*]
                eq = inner.index("=")
                segments.append(("filter_key", (inner[:eq].strip(), inner[eq + 1 :].strip())))
            elif "," in inner:
                # Multi-index: [0, 3, 7]
                indices = [int(x.strip()) for x in inner.split(",") if x.strip()]
                segments.append(("multi_index", indices))
            elif ":" in inner:
                # Slice: [0:5]
                parts = inner.split(":", 1)
                start = int(parts[0]) if parts[0].strip() else None
                end = int(parts[1]) if parts[1].strip() else None
                segments.append(("slice", (start, end)))
            elif inner.lstrip("-").isdigit():
                segments.append(("index", int(inner)))
            else:
                segments.append(("key", inner))
            i = j + 1

        # --- Context expansion: ~N (standalone, chainable) ---
        elif path[i] == "~" and i + 1 < n and path[i + 1].isdigit():
            i += 1
            j = i
            while j < n and path[j].isdigit():
                j += 1
            segments.append(("context", int(path[i:j])))
            i = j

        # --- Plain key name ---
        else:
            j = i
            while j < n and path[j] not in ".[(~":
                j += 1
            segments.append(("key", path[i:j]))
            i = j

    return segments


def _map_over_list(cur: list, segments: list[tuple[str, Any]], _root: Any = None) -> Any:
    """Apply *segments* to each item in *cur*, collecting and flattening results."""
    collected: list[Any] = []
    for item in cur:
        v = _resolve_path(item, segments, _root=_root)
        if v is None:
            continue
        if isinstance(v, list):
            collected.extend(v)
        else:
            collected.append(v)
    return collected if collected else None


def _recursive_find(obj: Any, key: str, context: int = 0) -> list[Any]:
    """Walk *obj* recursively, collecting every value where a dict key matches *key*.

    Supports glob patterns (``*``) for partial matching:
    - ``...*email*``  — any key containing "email"
    - ``...url*``     — any key starting with "url"
    - ``...*_at``     — any key ending with "_at"

    When *context* > 0, returns the ancestor subtree N levels above each match
    instead of just the matched value (``~N`` context expansion).

    Descends into dicts, lists, and auto-parses JSON strings.
    """
    is_pattern = "*" in key
    _match = (lambda k: fnmatch.fnmatchcase(k, key)) if is_pattern else (lambda k: k == key)

    if context == 0:
        # Fast path: no ancestry tracking needed
        results: list[Any] = []
        _recursive_walk_simple(obj, _match, results)
        return results

    # Context expansion: track ancestry for ~N
    results = []
    _recursive_walk_ctx(obj, _match, context, ancestry=[], results=results)
    return results


_MAX_RECURSION_DEPTH = 100


def _recursive_walk_simple(obj: Any, match: Any, results: list[Any], depth: int = 0) -> None:
    """Fast recursive walk — collects matched values without ancestry tracking."""
    if depth > _MAX_RECURSION_DEPTH:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and match(k):
                if isinstance(v, list):
                    results.extend(v)  # flatten list values
                else:
                    results.append(v)
            _recursive_walk_simple(v, match, results, depth=depth + 1)
    elif isinstance(obj, list):
        for item in obj:
            _recursive_walk_simple(item, match, results, depth=depth + 1)
    elif isinstance(obj, str) and obj.startswith(("{", "[")):
        try:
            _recursive_walk_simple(json.loads(obj), match, results, depth=depth + 1)
        except (json.JSONDecodeError, ValueError):
            pass


def _recursive_walk_ctx(
    obj: Any,
    match: Any,
    context: int,
    ancestry: list[Any],
    results: list[Any],
    depth: int = 0,
) -> None:
    """Recursive walk with ancestry tracking for ``~N`` context expansion.

    ~1 = parent dict, ~2 = grandparent, ~3 = great-grandparent, etc.
    When the ancestor level exceeds the tree depth, returns the root.
    """
    if depth > _MAX_RECURSION_DEPTH:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and match(k):
                if context <= 1:
                    results.append(obj)  # ~1 = the parent dict
                else:
                    idx = len(ancestry) - (context - 1)
                    idx = max(0, idx)
                    results.append(ancestry[idx] if idx < len(ancestry) else obj)
            ancestry.append(obj)
            try:
                _recursive_walk_ctx(v, match, context, ancestry, results, depth=depth + 1)
            finally:
                ancestry.pop()
    elif isinstance(obj, list):
        for item in obj:
            ancestry.append(obj)
            try:
                _recursive_walk_ctx(item, match, context, ancestry, results, depth=depth + 1)
            finally:
                ancestry.pop()
    elif isinstance(obj, str) and obj.startswith(("{", "[")):
        try:
            _recursive_walk_ctx(json.loads(obj), match, context, ancestry, results, depth=depth + 1)
        except (json.JSONDecodeError, ValueError):
            pass


def _find_value_ancestors(root: Any, targets: Any, n: int) -> list[Any]:
    """Find the ancestor N levels above each *target* value in the *root* tree.

    Uses identity (``id()``) to match target objects, so values must be the
    same Python objects as in the tree (not copies).
    """
    target_ids = {id(t) for t in (targets if isinstance(targets, list) else [targets])}
    results: list[Any] = []

    def _walk(obj: Any, ancestry: list[Any]) -> None:
        if id(obj) in target_ids:
            idx = max(0, len(ancestry) - n)
            results.append(
                ancestry[idx] if idx < len(ancestry) else ancestry[0] if ancestry else obj
            )
        if isinstance(obj, dict):
            for v in obj.values():
                ancestry.append(obj)
                _walk(v, ancestry)
                ancestry.pop()
        elif isinstance(obj, list):
            for item in obj:
                ancestry.append(obj)
                _walk(item, ancestry)
                ancestry.pop()

    _walk(root, [])
    return results


def _build_matcher(pattern: str):
    """Build a value matcher from a pattern string.

    Three modes:
    - ``/regex/``    — regex search (``re.search``)
    - ``*glob*``     — glob matching (``fnmatch``)
    - ``text``       — substring matching (``in``)

    Only matches scalar values (str, int, float, bool). Dicts and lists
    are skipped to avoid false positives from stringifying entire subtrees.
    """

    def _to_str(v: Any) -> str | None:
        if isinstance(v, str):
            return v
        if isinstance(v, (int, float, bool)):
            return str(v)
        return None  # skip dicts, lists, None

    if pattern.startswith("/") and pattern.endswith("/") and len(pattern) > 1:
        try:
            rx = re.compile(pattern[1:-1])
        except re.error as e:
            click.echo(f"Warning: invalid regex '{pattern}': {e}", err=True)
            return lambda v: False
        return lambda v: (s := _to_str(v)) is not None and rx.search(s) is not None
    if "*" in pattern:
        return lambda v: (s := _to_str(v)) is not None and fnmatch.fnmatchcase(s, pattern)
    return lambda v: (s := _to_str(v)) is not None and pattern in s


def _resolve_path(obj: Any, segments: list[tuple[str, Any]], _root: Any = None) -> Any:
    """Walk *obj* using parsed path segments.

    Segment types and their behavior:

    **Navigate** (maps over lists automatically):
    - ``("key", name)``       — dict key lookup
    - ``("keys", None)``      — all dict keys as a list
    - ``("values", None)``    — all dict values as a list
    - ``("recurse", name)``   — recursive search for key at any depth

    **Select** (picks from the container directly):
    - ``("index", n)``        — single element by position
    - ``("multi_index", [..])``— multiple elements by position
    - ``("slice", (a, b))``   — contiguous range

    **Context** (go up in the tree):
    - ``("context", n)``       — find ancestor N levels above current values

    JSON strings starting with ``{`` or ``[`` are auto-parsed before
    any operation, allowing traversal through embedded JSON
    (e.g. ``xhr.body.paths`` where body is a stringified JSON response).
    """
    root: Any = _root or obj  # preserve original root across recursive calls
    cur: Any = obj
    for i, (stype, sval) in enumerate(segments):
        # --- Auto-parse JSON strings before any operation ---
        if isinstance(cur, str) and cur.startswith(("{", "[")):
            try:
                cur = json.loads(cur)
            except (json.JSONDecodeError, ValueError):
                return None

        # ── Navigate operations (map over lists) ─────────────────────────

        if stype == "key":
            if isinstance(cur, dict):
                cur = cur.get(sval)
                if cur is None:
                    return None
            elif isinstance(cur, list):
                return _map_over_list(cur, segments[i:], _root=root)
            else:
                return None

        elif stype == "keys":
            if isinstance(cur, dict):
                cur = list(cur.keys())
            elif isinstance(cur, list):
                return _map_over_list(cur, segments[i:], _root=root)
            else:
                return None

        elif stype == "values":
            if isinstance(cur, dict):
                cur = list(cur.values())
            elif isinstance(cur, list):
                return _map_over_list(cur, segments[i:], _root=root)
            else:
                return None

        elif stype == "recurse":
            rkey, ctx = sval if isinstance(sval, tuple) else (sval, 0)
            found = _recursive_find(cur, rkey, context=ctx)
            if not found:
                return None
            rest = segments[i + 1 :]
            if rest:
                return _resolve_path(found, rest, _root=root)
            cur = found

        # ── Select operations (pick from container) ──────────────────────

        elif stype == "index":
            if isinstance(cur, list):
                try:
                    cur = cur[sval]
                except IndexError:
                    return None
            elif isinstance(cur, dict):
                try:
                    cur = cur[list(cur.keys())[sval]]
                except IndexError:
                    return None
            else:
                return None

        elif stype == "multi_index":
            if isinstance(cur, list):
                picked = []
                for idx in sval:
                    try:
                        picked.append(cur[idx])
                    except IndexError:
                        pass
                cur = picked if picked else None
                if cur is None:
                    return None
            elif isinstance(cur, dict):
                dk = list(cur.keys())
                picked = []
                for idx in sval:
                    try:
                        picked.append(cur[dk[idx]])
                    except IndexError:
                        pass
                cur = picked if picked else None
                if cur is None:
                    return None
            else:
                return None

        elif stype == "slice":
            start, end = sval
            if isinstance(cur, list):
                cur = cur[start:end]
            elif isinstance(cur, dict):
                keys = list(cur.keys())[start:end]
                cur = {k: cur[k] for k in keys}
            else:
                return None

        # ── Filter operations (keep matching items) ──────────────────────

        elif stype == "filter_value":
            # [=text], [=*glob*], or [=/regex/] — keep values matching
            _fmatch = _build_matcher(sval)
            if isinstance(cur, list):
                cur = [v for v in cur if v is not None and _fmatch(v)]
                if not cur:
                    return None
            elif cur is not None and not _fmatch(cur):
                return None

        elif stype == "filter_key":
            # [key=text], [key=*glob*], or [key=/regex/] — filter dicts
            # Key name supports glob: [*=faq] matches any key with value "faq"
            fkey, pattern = sval
            _fmatch = _build_matcher(pattern)
            _kmatch = _build_matcher(fkey) if "*" in fkey else None

            def _dict_matches(d: dict) -> bool:
                if _kmatch:
                    return any(_fmatch(v) for k, v in d.items() if _kmatch(k))
                return fkey in d and _fmatch(d[fkey])

            if isinstance(cur, list):
                filtered = [item for item in cur if isinstance(item, dict) and _dict_matches(item)]
                cur = filtered if filtered else None
                if cur is None:
                    return None
            elif isinstance(cur, dict):
                if not _dict_matches(cur):
                    return None
            else:
                return None

        elif stype == "filter_value_not":
            # [!=pattern] — keep values NOT matching
            _fmatch = _build_matcher(sval)
            if isinstance(cur, list):
                cur = [v for v in cur if v is not None and not _fmatch(v)]
                if not cur:
                    return None
            elif cur is not None and _fmatch(cur):
                return None

        elif stype == "filter_key_not":
            # [key!=pattern] — keep dicts where key does NOT match
            fkey, pattern = sval
            _fmatch = _build_matcher(pattern)
            _kmatch = _build_matcher(fkey) if "*" in fkey else None

            def _dict_excludes(d: dict) -> bool:
                if _kmatch:
                    return not any(_fmatch(v) for k, v in d.items() if _kmatch(k))
                return fkey not in d or not _fmatch(d[fkey])

            if isinstance(cur, list):
                filtered = [item for item in cur if isinstance(item, dict) and _dict_excludes(item)]
                cur = filtered if filtered else None
                if cur is None:
                    return None
            elif isinstance(cur, dict):
                if not _dict_excludes(cur):
                    return None
            else:
                return None

        # ── Context expansion (go up in the tree) ────────────────────────

        elif stype == "context":
            ancestors = _find_value_ancestors(root, cur, sval)
            cur = ancestors if ancestors else None
            if cur is None:
                return None

    # Final auto-parse: if the result is a JSON string, parse it
    if isinstance(cur, str) and cur.startswith(("{", "[")):
        try:
            cur = json.loads(cur)
        except (json.JSONDecodeError, ValueError):
            pass

    return cur


def _resolve_dotpath(obj: Any, keys: list[str]) -> Any:
    """Walk *obj* using dot-path key strings (backward-compatible interface).

    Converts ``["a", "b", "c"]`` to ``[("key", "a"), ("key", "b"), ("key", "c")]``
    and delegates to :func:`_resolve_path`.
    """
    segments = [("key", k) for k in keys]
    return _resolve_path(obj, segments)


def _parse_field_blocks(fields: str) -> list[tuple[str, str]]:
    """Parse a ``--fields`` value into ``(name, path)`` pairs.

    New format (``{name:path}`` blocks)::

        '{endpoints:paths[keys]},{title:info.title}'
        → [("endpoints", "paths[keys]"), ("title", "info.title")]

    Short form (no colon — last key segment becomes the name)::

        '{paths[keys]}'  → [("paths[keys]", "paths[keys]")]
        '{info.title}'   → [("title", "info.title")]

    Backward-compatible format (plain comma-separated, no braces)::

        'title,price'  → [("title", "title"), ("price", "price")]
    """
    fields = fields.strip()
    if not fields:
        return []

    # Backward compat: if no '{', split on commas (old format)
    if "{" not in fields:
        return [(f.strip(), f.strip()) for f in fields.split(",") if f.strip()]

    # New format: parse {} blocks
    result: list[tuple[str, str]] = []
    i = 0
    n = len(fields)
    while i < n:
        # Skip whitespace and commas between blocks
        while i < n and fields[i] in " ,\t":
            i += 1
        if i >= n:
            break
        if fields[i] != "{":
            # Stray text outside {} — skip to next { or end
            i += 1
            continue

        # Read from { to matching }, tracking () depth
        i += 1  # skip {
        depth = 0
        j = i
        while j < n:
            if fields[j] == "(":
                depth += 1
            elif fields[j] == ")":
                depth -= 1
            elif fields[j] == "}" and depth == 0:
                break
            j += 1
        block = fields[i:j].strip()
        i = j + 1  # skip }

        if not block:
            continue

        # Split on first ':' that's not inside []
        bracket_depth = 0
        colon_pos = -1
        for ci, ch in enumerate(block):
            if ch == "[":
                bracket_depth += 1
            elif ch == "]":
                bracket_depth -= 1
            elif ch == ":" and bracket_depth == 0:
                colon_pos = ci
                break

        if colon_pos >= 0:
            name = block[:colon_pos].strip()
            path = block[colon_pos + 1 :].strip()
        else:
            path = block
            # Derive name from last key segment
            segs = _parse_path(path)
            name = path
            for stype, sval in reversed(segs):
                if stype == "key":
                    name = sval
                    break
                if stype == "recurse":
                    name = sval[0] if isinstance(sval, tuple) else sval
                    break

        result.append((name, path))
    return result


_NEEDS_ESCAPE = set(".[](){}… ")  # chars in key names that need (escaping)


def _format_key(prefix: str, key: str) -> str:
    """Format a dict key for hint display, using ``(escaped)`` if needed."""
    if any(c in key for c in _NEEDS_ESCAPE):
        segment = f"({key})"
    else:
        segment = key
    return f"{prefix}.{segment}" if prefix else segment


def _collect_dotpaths(obj: Any, prefix: str = "", max_depth: int = 4) -> list[str]:
    """Recursively collect all valid paths from a JSON object for hint messages.

    Shows dot-paths for dict keys (with ``(escaped)`` for special chars),
    ``[0]`` for arrays, ``[keys]``/``[values]`` for dicts, ``...key`` hint
    for recursive search, and peeks into JSON strings.
    """
    if max_depth <= 0:
        return []
    paths: list[str] = []
    if isinstance(obj, dict):
        paths.append(f"{prefix}[keys]" if prefix else "[keys]")
        paths.append(f"{prefix}[values]" if prefix else "[values]")
        for key in obj.keys():
            full = _format_key(prefix, key)
            paths.append(full)
            paths.extend(_collect_dotpaths(obj[key], full, max_depth - 1))
    elif isinstance(obj, list) and obj:
        for idx in range(min(len(obj), 3)):
            paths.append(f"{prefix}[{idx}]" if prefix else f"[{idx}]")
        if isinstance(obj[0], dict):
            paths.extend(_collect_dotpaths(obj[0], prefix, max_depth - 1))
    elif isinstance(obj, str) and obj.startswith(("{", "[")):
        try:
            parsed = json.loads(obj)
            paths.extend(_collect_dotpaths(parsed, prefix, max_depth - 1))
        except (json.JSONDecodeError, ValueError):
            pass
    return paths


def _resolve_single_part(obj: Any, part: str) -> Any:
    """Resolve one part of an expression.

    Uses ``_parse_path`` + ``_resolve_path``. Value filters are handled
    via ``[=pattern]`` and ``[key=pattern]`` bracket operations inside the path.
    """
    segments = _parse_path(part)
    return _resolve_path(obj, segments)


def resolve_expression(obj: Any, expression: str) -> Any:
    """Evaluate a full extraction expression with ``|``, ``&``, and ``=`` support.

    Expression syntax:
    - ``path``                  — single path
    - ``path=pattern``          — single path with value filter
    - ``path1 | path2 | ...``   — OR: combine all results
    - ``path1 & path2 & ...``   — AND: output only if ALL parts match

    Cannot mix ``|`` and ``&`` in one expression.
    """
    has_or = " | " in expression
    has_and = " & " in expression

    if has_or and has_and:
        click.echo(
            "Error: Cannot mix | and & in one expression. Use one or the other.",
            err=True,
        )
        return None

    if has_or:
        parts = [p.strip() for p in expression.split(" | ")]
        combined: list[Any] = []
        for part in parts:
            result = _resolve_single_part(obj, part)
            if result is not None:
                if isinstance(result, list):
                    combined.extend(result)
                else:
                    combined.append(result)
        return combined if combined else None

    if has_and:
        parts = [p.strip() for p in expression.split(" & ")]
        all_results: list[tuple[str, Any]] = []
        for part in parts:
            result = _resolve_single_part(obj, part)
            if result is None:
                return None  # AND fails — one part didn't match
            all_results.append((part, result))
        # All matched — combine all results
        combined = []
        for _, result in all_results:
            if isinstance(result, list):
                combined.extend(result)
            else:
                combined.append(result)
        return combined if combined else None

    # Single expression (no | or &)
    return _resolve_single_part(obj, expression)


def _extract_field_values(data: bytes, path: str) -> bytes:
    """Extract values from JSON data using the path expression language.

    Supports the full syntax: dot notation, brackets, recursive search,
    glob patterns, context expansion, ``|`` OR, ``&`` AND, and ``=`` value filter.

    Returns newline-separated UTF-8 bytes for scalar/list results,
    or JSON bytes for dict results. Returns empty bytes if not found.
    """
    try:
        obj = json.loads(data.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return data

    result = resolve_expression(obj, path)

    if result is None:
        hints = _collect_dotpaths(obj)
        hint = ""
        if hints:
            hint = "\n  Available paths:\n    " + "\n    ".join(hints)
        click.echo(
            f"Warning: --extract-field '{path}' did not match any data.{hint}",
            err=True,
        )
        return b""

    def _serialize(v: Any) -> str:
        if isinstance(v, (dict, list)):
            return json.dumps(v, ensure_ascii=False)
        return str(v)

    if isinstance(result, list):
        values = [_serialize(v) for v in result if v is not None]
    else:
        values = [_serialize(result)]

    return ("\n".join(values) + "\n").encode("utf-8") if values else b""


def _filter_fields(data: bytes, fields: str) -> bytes:
    """Filter JSON output using the path language.

    Supports two formats:

    New ``{name:path}`` block syntax (full path language)::

        '{endpoints:paths[keys]},{title:info.title}'

    Backward-compatible plain comma-separated fields::

        'title,price'

    For list inputs (e.g. batch results), each item is filtered independently.
    Returns filtered JSON bytes. Returns *data* unchanged if parsing fails.
    """
    blocks = _parse_field_blocks(fields)
    if not blocks:
        return data
    try:
        obj = json.loads(data.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return data

    def _apply_blocks(target: Any) -> Any:
        """Resolve all field blocks against *target*, return a named dict."""
        result: dict = {}
        for name, path_str in blocks:
            segments = _parse_path(path_str)
            val = _resolve_path(target, segments)
            if val is not None:
                result[name] = val
        return result

    if isinstance(obj, list):
        filtered = [_apply_blocks(item) for item in obj]
    else:
        filtered = _apply_blocks(obj)

    # Warn about blocks that didn't match any data
    if isinstance(filtered, dict):
        for name, path_str in blocks:
            if name not in filtered:
                available = _collect_dotpaths(obj)
                hint = ""
                if available:
                    hint = "\n  Available paths:\n    " + "\n    ".join(available)
                click.echo(
                    f"Warning: --fields '{path_str}' did not match any data.{hint}",
                    err=True,
                )
                break  # Only warn once

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
    output_file: str = "",
    succeeded: int = 0,
    failed: int = 0,
) -> None:
    """Run the ``--on-complete`` shell command if set.

    Injects ``SCRAPINGBEE_OUTPUT_DIR`` (individual files mode),
    ``SCRAPINGBEE_OUTPUT_FILE`` (csv/ndjson/update-csv mode),
    ``SCRAPINGBEE_SUCCEEDED``, and ``SCRAPINGBEE_FAILED`` environment variables.
    """
    if not cmd:
        return
    import os
    import subprocess

    from .audit import log_exec
    from .exec_gate import require_exec

    require_exec("--on-complete", cmd)
    log_exec("on-complete", cmd, output_dir=output_dir or output_file)
    click.echo(f"⚠ Executing: {cmd.split()[0] if cmd.split() else cmd} (whitelisted)", err=True)

    env = os.environ.copy()
    env["SCRAPINGBEE_OUTPUT_DIR"] = output_dir
    env["SCRAPINGBEE_OUTPUT_FILE"] = output_file
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
    smart_extract: str | None = None,
    extract_field: str | None = None,
    fields: str | None = None,
    command: str | None = None,
    credit_cost: int | None = None,
) -> None:
    """Write response data to file or stdout; optionally print verbose headers.

    When *smart_extract* is set, auto-detect format and extract using the path
    language. When *extract_field* is set, extract from JSON using a path
    expression. When *fields* is set, filter JSON to specified fields.
    Precedence: *smart_extract* > *extract_field* > *fields*.
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
    if smart_extract:
        from .extract import smart_extract as _smart_extract_fn

        data = _smart_extract_fn(data, smart_extract)
    elif extract_field:
        data = _extract_field_values(data, extract_field)
    elif fields:
        data = _filter_fields(data, fields)
    if output_path:
        try:
            fh = open(output_path, "wb")
        except OSError as e:
            click.echo(f"Cannot write to '{output_path}': {e.strerror}", err=True)
            raise SystemExit(1)
        with fh:
            fh.write(data)
    else:
        sys.stdout.buffer.write(data)
        # Only add a trailing newline for text-like content; binary data (PNG, PDF, etc.)
        # must not have extra bytes appended.
        if data and not data.endswith(b"\n"):
            is_text = data[:1] in (b"{", b"[", b"<", b"#") or b"\x00" not in data[:512]
            if is_text:
                click.echo()
