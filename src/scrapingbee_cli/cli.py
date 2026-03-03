"""ScrapingBee CLI - click entrypoint and commands."""

from __future__ import annotations

from typing import Any

import click

from . import __version__
from .commands import register_commands
from .config import load_dotenv


def _global_options(f: Any) -> Any:
    f = click.option(
        "--output-file",
        "output_file",
        type=click.Path(),
        default=None,
        help="Write output to file instead of stdout",
    )(f)
    f = click.option(
        "--verbose",
        is_flag=True,
        default=False,
        help="Show response headers and status code",
    )(f)
    f = click.option(
        "--output-dir",
        "output_dir",
        default=None,
        help="Batch/crawl: folder for output files (default: batch_<timestamp> or crawl_<timestamp>)",
    )(f)
    f = click.option(
        "--input-file",
        "input_file",
        type=str,
        default=None,
        help="Batch: one item per line (URL, query, ASIN, etc. depending on command). Use - for stdin.",
    )(f)
    f = click.option(
        "--concurrency",
        type=int,
        default=0,
        help="Batch mode: max concurrent requests (0 = use limit from usage API)",
    )(f)
    f = click.option(
        "--retries",
        type=int,
        default=3,
        help="Retry on 5xx or connection errors (default: 3). Applies to usage and search endpoints.",
    )(f)
    f = click.option(
        "--backoff",
        type=float,
        default=2.0,
        help="Backoff multiplier for retries (default: 2.0). Delay = backoff^attempt seconds.",
    )(f)
    f = click.option(
        "--resume",
        is_flag=True,
        default=False,
        help=(
            "Resume a previous batch or crawl: skip items already saved in --output-dir. "
            "Requires --output-dir pointing to the previous run folder."
        ),
    )(f)
    f = click.option(
        "--no-progress",
        "no_progress",
        is_flag=True,
        default=False,
        help="Suppress per-item progress counter during batch runs.",
    )(f)
    f = click.option(
        "--extract-field",
        "extract_field",
        type=str,
        default=None,
        help=(
            "Extract values from JSON response using a dot path and output "
            "one value per line (e.g. 'organic_results.url' or 'title'). "
            "Useful for piping SERP/search results into --input-file."
        ),
    )(f)
    f = click.option(
        "--fields",
        type=str,
        default=None,
        help=(
            "Comma-separated top-level JSON keys to include in output "
            "(e.g. 'title,price,rating'). Filters single-item responses. "
            "Ignored when --extract-field is set."
        ),
    )(f)
    f = click.option(
        "--diff-dir",
        "diff_dir",
        type=click.Path(exists=True, file_okay=False),
        default=None,
        help=(
            "Batch: compare with a previous run's output directory. "
            "Files whose content is unchanged are not re-written; manifest marks them unchanged=true."
        ),
    )(f)
    return f


@click.group()
@click.version_option(version=__version__)
@_global_options
@click.pass_context
def cli(
    ctx: click.Context,
    output_file: str | None,
    verbose: bool,
    output_dir: str | None,
    input_file: str | None,
    concurrency: int,
    retries: int,
    backoff: float,
    resume: bool,
    no_progress: bool,
    extract_field: str | None,
    fields: str | None,
    diff_dir: str | None,
) -> None:
    """ScrapingBee CLI - Web scraping API client.

    Commands: scrape (single or batch), crawl (Scrapy/quick-crawl), usage,
    Google Search, Fast Search, Amazon, Walmart, YouTube, and ChatGPT.

    Authenticate with `scrapingbee auth` or set SCRAPINGBEE_API_KEY (env / .env).
    """
    load_dotenv()
    ctx.ensure_object(dict)
    ctx.obj["output_file"] = output_file
    ctx.obj["verbose"] = verbose
    # Global --output-dir: used by both batch and crawl when their local --output-dir is not set
    ctx.obj["output_dir"] = output_dir or ""
    ctx.obj["input_file"] = input_file
    ctx.obj["concurrency"] = concurrency or 0
    ctx.obj["retries"] = retries if retries is not None else 3
    ctx.obj["backoff"] = backoff if backoff is not None else 2.0
    ctx.obj["resume"] = resume
    ctx.obj["progress"] = not no_progress
    ctx.obj["extract_field"] = extract_field
    ctx.obj["fields"] = fields
    ctx.obj["diff_dir"] = diff_dir


register_commands(cli)

# ---------------------------------------------------------------------------
# Global-option reordering: let users place global flags after the subcommand
# ---------------------------------------------------------------------------

_GLOBAL_OPTION_SPECS: dict[str, bool] = {  # name → takes_value
    "--output-file": True,
    "--verbose": False,
    "--output-dir": True,
    "--input-file": True,
    "--concurrency": True,
    "--retries": True,
    "--backoff": True,
    "--resume": False,
    "--no-progress": False,
    "--extract-field": True,
    "--fields": True,
    "--diff-dir": True,
}

_SUBCOMMAND_NAMES = frozenset(
    {
        "usage",
        "auth",
        "docs",
        "logout",
        "scrape",
        "crawl",
        "google",
        "fast-search",
        "amazon-product",
        "amazon-search",
        "walmart-search",
        "walmart-product",
        "youtube-search",
        "youtube-metadata",
        "chatgpt",
        "export",
        "schedule",
    }
)

_NO_REORDER = frozenset({"schedule"})  # passes raw args to subprocess

# Options that exist on both the group level *and* a specific subcommand.
# When the subcommand matches, leave the option in place (it belongs to the subcommand).
_SUBCOMMAND_COLLISIONS: dict[str, frozenset[str]] = {
    "export": frozenset({"--diff-dir"}),
}


def _reorder_global_options(argv: list[str]) -> list[str]:
    """Move global options that appear after the subcommand to before it.

    This lets users write ``scrapingbee google --verbose "query"`` instead of
    requiring ``scrapingbee --verbose google "query"``.
    """
    if not argv:
        return argv

    # Phase 1 — find the subcommand index, skipping global options + their values
    sub_idx: int | None = None
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok in _GLOBAL_OPTION_SPECS:
            i += 1  # skip the option itself
            if _GLOBAL_OPTION_SPECS[tok]:  # takes a value — skip the value too
                i += 1
            continue
        if tok in _SUBCOMMAND_NAMES:
            sub_idx = i
            break
        # Not a global option and not a subcommand (e.g. --help, --version)
        break
    # end while

    if sub_idx is None:
        return argv  # no subcommand found (--help, --version, etc.)

    subcmd = argv[sub_idx]
    if subcmd in _NO_REORDER:
        return argv  # schedule passes raw args to subprocess

    collisions = _SUBCOMMAND_COLLISIONS.get(subcmd, frozenset())

    # Phase 2 — scan args after the subcommand, move global options to before it
    before = list(argv[:sub_idx])
    after_cmd: list[str] = []
    moved: list[str] = []

    j = sub_idx + 1
    while j < len(argv):
        tok = argv[j]
        if tok in _GLOBAL_OPTION_SPECS and tok not in collisions:
            moved.append(tok)
            j += 1
            if _GLOBAL_OPTION_SPECS[tok] and j < len(argv):
                moved.append(argv[j])
                j += 1
        else:
            after_cmd.append(tok)
            j += 1

    return before + moved + [subcmd] + after_cmd


def _reject_equals_syntax() -> None:
    """Reject --option=value; require --option value (space-separated)."""
    import sys

    for arg in sys.argv[1:]:
        if arg.startswith("--") and "=" in arg:
            opt = arg.split("=", 1)[0]
            click.echo(
                f"Use space-separated values: '{opt} VALUE' instead of '{arg}'.",
                err=True,
            )
            sys.exit(2)


def main() -> None:
    """Entry point for scrapingbee console script."""
    import sys

    sys.argv[1:] = _reorder_global_options(sys.argv[1:])
    _reject_equals_syntax()
    try:
        cli.main(standalone_mode=False)
    except click.UsageError as e:
        msg = str(e)
        if "No such option: -o" in msg:
            e = click.UsageError(
                "No such option: -o. Use global --output-file before the command, "
                "e.g. scrapingbee --output-file FILE scrape URL.",
                e.ctx,
            )
        elif "No such option: -v" in msg:
            e = click.UsageError(
                "No such option: -v. Use global --verbose before the command, "
                "e.g. scrapingbee --verbose scrape URL.",
                e.ctx,
            )
        elif "No such option: --output-dir" in msg:
            e = click.UsageError(
                "No such option: --output-dir. Use global --output-dir before the command, "
                "e.g. scrapingbee --output-dir DIR --input-file urls.txt scrape.",
                e.ctx,
            )
        e.show()
        sys.exit(2)
    except click.ClickException as e:
        e.show()
        sys.exit(e.exit_code)
    except SystemExit as e:
        sys.exit(e.code if e.code is not None else 0)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
