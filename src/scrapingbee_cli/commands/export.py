"""Export command: merge batch or crawl output files into a single ndjson, txt, or csv file."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import click


@click.command("export")
@click.option(
    "--input-dir",
    required=True,
    type=click.Path(exists=True, file_okay=False),
    help="Batch or crawl output directory to read from.",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["ndjson", "txt", "csv"], case_sensitive=False),
    default="ndjson",
    show_default=True,
    help="Output format: ndjson (one JSON object per line), txt (plain text blocks), or csv (flat table from JSON arrays).",
)
@click.option(
    "--flatten",
    is_flag=True,
    default=False,
    help="CSV: recursively flatten nested dicts to dot-notation columns (e.g. buybox.price).",
)
@click.option(
    "--deduplicate",
    "deduplicate_rows",
    is_flag=True,
    default=False,
    help="CSV: remove duplicate rows.",
)
@click.option(
    "--columns",
    type=str,
    default=None,
    help="CSV: comma-separated column names to include. Rows missing all selected columns are dropped.",
)
@click.option(
    "--output-file",
    "output_file",
    type=click.Path(),
    default=None,
    help="Write output to file instead of stdout.",
)
@click.pass_obj
def export_cmd(
    obj: dict,
    input_dir: str,
    fmt: str,
    flatten: bool,
    deduplicate_rows: bool,
    columns: str | None,
    output_file: str | None,
) -> None:
    """Merge numbered output files from a batch or crawl into a single stream.

    Reads manifest.json (if present) to annotate each record with its source URL.
    Without manifest.json, processes all N.ext files in numeric order.

    Use --output-file to write to a file (default: stdout).

    \b
    Examples:
      scrapingbee export --input-dir batch_20250101_120000 --output-file all.ndjson
      scrapingbee export --input-dir crawl_20250101 --format txt --output-file pages.txt
      scrapingbee export --input-dir serps/ --format csv --flatten --output-file results.csv
    """
    if output_file is not None:
        obj["output_file"] = output_file
    input_path = Path(input_dir).resolve()
    output_file = obj.get("output_file")

    # Load manifest for URL → relative-path mapping (optional)
    # Supports both old format (string values) and new format (dict values with "file" key).
    file_to_url: dict[str, str] = {}
    manifest_path = input_path / "manifest.json"
    if manifest_path.is_file():
        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest: dict[str, object] = json.load(f)
            for url, val in manifest.items():
                if isinstance(val, str):
                    file_to_url[val] = url  # old format: url → "N.json"
                elif isinstance(val, dict) and "file" in val:
                    file_to_url[val["file"]] = url  # new format: url → {file, ...}
        except Exception as e:
            click.echo(f"Warning: could not read manifest.json: {e}", err=True)

    # Collect N.ext files (not .err), recursively
    entries: list[tuple[int, Path, str]] = []
    for p in input_path.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lstrip(".") == "err":
            continue
        try:
            n = int(p.stem)
        except ValueError:
            continue
        rel = str(p.relative_to(input_path))
        entries.append((n, p, rel))

    entries.sort(key=lambda x: x[0])

    if not entries:
        click.echo("No output files found in directory.", err=True)
        raise SystemExit(1)

    if fmt == "csv":
        _export_csv(
            entries,
            file_to_url,
            output_file,
            flatten=flatten,
            deduplicate_rows=deduplicate_rows,
            columns=columns,
        )
        return

    out_lines: list[str] = []
    for n, p, rel in entries:
        try:
            content = p.read_bytes()
        except Exception as e:
            click.echo(f"Warning: could not read {p}: {e}", err=True)
            continue
        url = file_to_url.get(rel, "")

        if fmt == "ndjson":
            try:
                obj_data = json.loads(content.decode("utf-8", errors="replace"))
                if url:
                    if isinstance(obj_data, dict):
                        obj_data.setdefault("_url", url)
                    else:
                        obj_data = {"_url": url, "data": obj_data}
                out_lines.append(json.dumps(obj_data, ensure_ascii=False))
            except (json.JSONDecodeError, UnicodeDecodeError):
                text = content.decode("utf-8", errors="replace")
                record: dict = {"content": text}
                if url:
                    record["_url"] = url
                out_lines.append(json.dumps(record, ensure_ascii=False))
        else:  # txt
            if url:
                out_lines.append(f"# {url}")
            text = content.decode("utf-8", errors="replace")
            out_lines.extend(text.splitlines())
            out_lines.append("")  # blank separator between documents

    output = "\n".join(out_lines)
    if fmt == "txt":
        output = output.rstrip("\n")

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(output + "\n")
        click.echo(f"Exported {len(entries)} files to {output_file}", err=True)
    else:
        click.echo(output)


def _find_main_list(data: dict) -> list[dict] | None:
    """Return the largest top-level list of dicts in a JSON object, or None.
    Only returns a list if the object looks like a search/collection result
    (the list is a significant portion of the object's data). Single-item
    detail pages (product, video metadata) should be exported as one row,
    not expanded into their nested review/variant arrays."""
    # Count scalar (non-collection) top-level keys
    scalar_keys = sum(1 for v in data.values() if not isinstance(v, (dict, list)))
    best: list[dict] | None = None
    best_key: str | None = None
    best_len = 0
    for k, v in data.items():
        if not isinstance(v, list) or len(v) <= best_len:
            continue
        if any(isinstance(x, dict) for x in v):
            best = [x for x in v if isinstance(x, dict)]
            best_key = k
            best_len = len(best)
    if best is None:
        return None
    # Heuristic: if the object has many scalar fields alongside the list,
    # it's likely a detail page (product, video) — treat as single row.
    # Search results typically have few scalar keys and one dominant list.
    if scalar_keys > 8 and best_key not in ("results", "products", "organic_results", "items"):
        return None
    return best


def _flatten_value(v: object) -> str:
    """Serialise nested dicts/lists as JSON strings; leave scalars as-is."""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    if v is None:
        return ""
    return str(v)


def _flatten_dict(d: dict, prefix: str = "", sep: str = ".") -> dict[str, str]:
    """Recursively flatten a nested dict into dot-notation keys with scalar string values.
    Lists of scalars are joined with ' | '. Lists of dicts are indexed:
    buybox.0.price, buybox.0.seller_name, buybox.1.price, etc."""
    result: dict[str, str] = {}
    for k, v in d.items():
        key = f"{prefix}{sep}{k}" if prefix else k
        if isinstance(v, dict):
            result.update(_flatten_dict(v, key, sep))
        elif isinstance(v, list):
            if not v:
                result[key] = ""
            elif any(isinstance(x, (dict, list)) for x in v):
                # List contains dicts or nested lists — index-expand
                for i, item in enumerate(v):
                    if isinstance(item, dict):
                        result.update(_flatten_dict(item, f"{key}.{i}", sep))
                    elif isinstance(item, list):
                        result[f"{key}.{i}"] = json.dumps(item, ensure_ascii=False)
                    elif item is None:
                        result[f"{key}.{i}"] = ""
                    else:
                        result[f"{key}.{i}"] = str(item)
            else:
                # Plain list of scalars — keep as-is
                result[key] = str(v)
        elif v is None:
            result[key] = ""
        else:
            result[key] = str(v)
    return result


def _export_csv(
    entries: list[tuple[int, Path, str]],
    file_to_url: dict[str, str],
    output_file: str | None,
    *,
    flatten: bool = False,
    deduplicate_rows: bool = False,
    columns: str | None = None,
) -> None:
    """Flatten JSON files to CSV rows and write output."""
    rows: list[dict] = []

    for _n, p, rel in entries:
        if p.suffix.lower() != ".json":
            continue
        try:
            data = json.loads(p.read_bytes().decode("utf-8", errors="replace"))
        except Exception as e:
            click.echo(f"Warning: could not parse {p}: {e}", err=True)
            continue
        url = file_to_url.get(rel, "")

        if isinstance(data, list):
            file_rows: list[dict] = [x for x in data if isinstance(x, dict)]
        elif isinstance(data, dict):
            main = _find_main_list(data)
            file_rows = main if main is not None else [data]
        else:
            continue  # scalar — skip

        for row in file_rows:
            if flatten:
                flat = _flatten_dict(row)
            else:
                flat = {k: _flatten_value(v) for k, v in row.items()}
            if url:
                flat = {"_url": url, **flat}
            rows.append(flat)

    if not rows:
        click.echo("No JSON data found for CSV export.", err=True)
        raise SystemExit(1)

    if deduplicate_rows:
        seen: set[tuple[tuple[str, str], ...]] = set()
        deduped: list[dict] = []
        for row in rows:
            key = tuple(sorted(row.items()))
            if key not in seen:
                seen.add(key)
                deduped.append(row)
        removed = len(rows) - len(deduped)
        if removed:
            click.echo(f"Removed {removed} duplicate row(s).", err=True)
        rows = deduped

    # Apply --columns filter
    if columns:
        selected = [c.strip() for c in columns.split(",") if c.strip()]
        # Drop rows that have none of the selected columns populated
        filtered = []
        for row in rows:
            if any(row.get(c) for c in selected):
                filtered.append({k: v for k, v in row.items() if k in selected or k == "_url"})
        dropped = len(rows) - len(filtered)
        if dropped:
            click.echo(f"Dropped {dropped} row(s) missing all selected columns.", err=True)
        rows = filtered
        fieldnames = (["_url"] if any("_url" in r for r in rows) else []) + selected
    else:
        # Collect all column names in insertion order
        all_keys: dict[str, None] = {}
        for row in rows:
            all_keys.update({k: None for k in row})
        fieldnames = list(all_keys)

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    output = buf.getvalue()

    if output_file:
        with open(output_file, "w", encoding="utf-8", newline="") as f:
            f.write(output)
        click.echo(f"Exported {len(rows)} rows to {output_file}", err=True)
    else:
        click.echo(output, nl=False)


def register(cli: click.Group) -> None:
    cli.add_command(export_cmd, "export")
