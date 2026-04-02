"""ScrapingBee CLI - click entrypoint and commands."""

from __future__ import annotations

import click

from . import __version__
from .commands import register_commands
from .config import load_dotenv


def _show_active_schedules_hint() -> None:
    """If there are active schedules, print a one-line hint to stderr."""
    import json
    import sys
    from pathlib import Path

    # Skip when running schedule command itself (avoids redundant output)
    if "schedule" in sys.argv[1:3]:
        return
    # Skip for --help and --version
    if "--help" in sys.argv or "--version" in sys.argv:
        return

    from datetime import datetime

    registry_path = Path.home() / ".config" / "scrapingbee-cli" / "schedules.json"
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception:
        return
    if not registry:
        return

    parts = []
    now = datetime.now()
    for name, info in registry.items():
        since = ""
        created = info.get("created_at", "")
        if created:
            try:
                dt = datetime.strptime(created, "%Y-%m-%d %H:%M:%S")
                delta = now - dt
                total_s = int(delta.total_seconds())
                if total_s < 60:
                    since = f" (running {total_s}s)"
                elif total_s < 3600:
                    since = f" (running {total_s // 60}m)"
                elif total_s < 86400:
                    h, m = divmod(total_s // 60, 60)
                    since = f" (running {h}h {m}m)"
                else:
                    d, h = divmod(total_s // 3600, 24)
                    since = f" (running {d}d {h}h)"
            except ValueError:
                pass
        parts.append(f"{name}{since}")

    click.echo(
        f"Info: {len(registry)} active schedule(s): {', '.join(parts)}. "
        "Run 'scrapingbee schedule --list' for details.",
        err=True,
    )


@click.group()
@click.version_option(version=__version__)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """ScrapingBee CLI - Web scraping API client.

    Commands: scrape (single or batch), crawl (Scrapy/quick-crawl), usage,
    Google Search, Fast Search, Amazon, Walmart, YouTube, and ChatGPT.

    Authenticate with `scrapingbee auth` or set SCRAPINGBEE_API_KEY (env / .env).
    """
    load_dotenv()
    _show_active_schedules_hint()
    ctx.ensure_object(dict)


register_commands(cli)


def _handle_resume() -> bool:
    """Handle `scrapingbee --resume` — list incomplete batches. Returns True if handled."""
    import sys

    if "--resume" not in sys.argv or len(sys.argv) > 2:
        return False
    # Only handle bare `scrapingbee --resume`
    if sys.argv[1:] != ["--resume"]:
        return False

    from .batch import find_incomplete_batches

    batches = find_incomplete_batches()
    if not batches:
        click.echo("No incomplete batches found in current directory.", err=True)
        return True

    click.echo(f"Found {len(batches)} incomplete batch(es):\n", err=True)
    for i, b in enumerate(batches, 1):
        remaining = b["total"] - b["succeeded"]
        click.echo(
            f"  [{i}] {b['dir']}/  —  {b['succeeded']}/{b['total']} complete, "
            f"{remaining} remaining",
            err=True,
        )
        import shlex

        cmd = b["command"]
        if cmd and "--resume" not in cmd:
            cmd += " --resume"
        if cmd and "--output-dir" not in cmd:
            cmd += f" --output-dir {shlex.quote(b['dir'])}"
        if cmd:
            click.echo(f"      {cmd}", err=True)
        click.echo("", err=True)
    return True


def _handle_scraping_config() -> None:
    """Handle `scrapingbee --scraping-config NAME [...]` — auto-route to scrape command."""
    import sys

    if "--scraping-config" not in sys.argv:
        return
    args = sys.argv[1:]
    if not args:
        return
    # Check if a subcommand is already specified before --scraping-config
    # Known subcommands that could appear first
    commands = {
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
        "usage",
        "auth",
        "logout",
        "docs",
        "schedule",
        "export",
        "unsafe",
    }
    for a in args:
        if a in commands:
            return  # Subcommand already specified, let Click handle it
        if a == "--scraping-config":
            break  # --scraping-config comes before any subcommand
    # No subcommand — inject "scrape" before the args
    sys.argv = [sys.argv[0], "scrape"] + args


def main() -> None:
    """Entry point for scrapingbee console script."""
    import asyncio
    import sys

    if _handle_resume():
        sys.exit(0)
    _handle_scraping_config()

    try:
        cli.main(standalone_mode=False)
    except click.ClickException as e:
        e.show()
        sys.exit(e.exit_code)
    except SystemExit as e:
        sys.exit(e.code if e.code is not None else 0)
    except KeyboardInterrupt:
        click.echo("\nInterrupted.", err=True)
        sys.exit(130)
    except OSError as e:
        # Network errors, DNS failures, connection refused, etc.
        click.echo(f"Connection error: {e}", err=True)
        sys.exit(1)
    except asyncio.TimeoutError:
        click.echo("Request timed out. Check your internet connection or try again.", err=True)
        sys.exit(1)
    except Exception as e:
        # Catch-all for unexpected errors — show a clean message, not a traceback
        err_type = type(e).__name__
        click.echo(f"Error: {err_type}: {e}", err=True)
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
