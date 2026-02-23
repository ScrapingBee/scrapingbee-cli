"""ScrapingBee CLI - click entrypoint and commands."""

from __future__ import annotations

from typing import Any

import click
from click_option_group import optgroup

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
        type=click.Path(exists=True),
        default=None,
        help="Batch: one item per line (URL, query, ASIN, etc. depending on command)",
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


register_commands(cli)


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
