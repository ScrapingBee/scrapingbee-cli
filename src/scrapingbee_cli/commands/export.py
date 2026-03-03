"""Export command: merge batch or crawl output files into a single ndjson, txt, or csv file."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path

import click


def _file_md5(path: Path) -> str:
    """Return MD5 hex digest of file contents."""
    return hashlib.md5(path.read_bytes()).hexdigest()


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
    "--diff-dir",
    "diff_dir",
    type=click.Path(exists=True, file_okay=False),
    default=None,
    help=(
        "Compare with a previous batch/crawl directory and output only changed or new items. "
        "Items whose file content is identical to the corresponding file in --diff-dir are skipped."
    ),
)
@click.pass_obj
def export_cmd(
    obj: dict,
    input_dir: str,
    fmt: str,
    diff_dir: str | None,
) -> None:
    """Merge numbered output files from a batch or crawl into a single stream.

    Reads manifest.json (if present) to annotate each record with its source URL.
    Without manifest.json, processes all N.ext files in numeric order.

    Use global --output-file to write to a file (default: stdout).
    Use --diff-dir to output only items that changed since a previous run.

    \b
    Examples:
      scrapingbee --output-file all.ndjson export --input-dir batch_20250101_120000
      scrapingbee --output-file pages.txt export --input-dir crawl_20250101 --format txt
      scrapingbee --output-file results.csv export --input-dir serps/ --format csv
      scrapingbee export --input-dir new_batch/ --diff-dir old_batch/ --format ndjson
    """
    input_path = Path(input_dir).resolve()
    output_file: str | None = obj.get("output_file")

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

    # Build hash map from --diff-dir for change detection
    old_hashes: dict[str, str] = {}  # numeric stem → md5
    if diff_dir:
        diff_path = Path(diff_dir).resolve()
        for p in diff_path.rglob("*"):
            if p.is_file() and p.suffix.lstrip(".") != "err":
                try:
                    int(p.stem)
                    old_hashes[p.stem] = _file_md5(p)
                except ValueError:
                    continue

    # Collect N.ext files (not .err), recursively; apply --diff-dir filtering
    entries: list[tuple[int, Path, str]] = []
    skipped_unchanged = 0
    for p in input_path.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lstrip(".") == "err":
            continue
        try:
            n = int(p.stem)
        except ValueError:
            continue
        if old_hashes and p.stem in old_hashes and _file_md5(p) == old_hashes[p.stem]:
            skipped_unchanged += 1
            continue
        rel = str(p.relative_to(input_path))
        entries.append((n, p, rel))

    entries.sort(key=lambda x: x[0])

    if skipped_unchanged:
        click.echo(f"Skipped {skipped_unchanged} unchanged item(s) (--diff-dir).", err=True)

    if not entries:
        click.echo("No output files found in directory.", err=True)
        raise SystemExit(1)

    if fmt == "csv":
        _export_csv(entries, file_to_url, output_file)
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
    """Return the largest top-level list of dicts in a JSON object, or None."""
    best: list[dict] | None = None
    best_len = 0
    for v in data.values():
        if not isinstance(v, list) or len(v) <= best_len:
            continue
        # Require at least one dict element
        if any(isinstance(x, dict) for x in v):
            best = [x for x in v if isinstance(x, dict)]
            best_len = len(best)
    return best


def _flatten_value(v: object) -> str:
    """Serialise nested dicts/lists as JSON strings; leave scalars as-is."""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    if v is None:
        return ""
    return str(v)


def _export_csv(
    entries: list[tuple[int, Path, str]],
    file_to_url: dict[str, str],
    output_file: str | None,
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
            flat = {k: _flatten_value(v) for k, v in row.items()}
            if url:
                flat = {"_url": url, **flat}
            rows.append(flat)

    if not rows:
        click.echo("No JSON data found for CSV export.", err=True)
        raise SystemExit(1)

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
