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


def main() -> None:
    """Entry point for scrapingbee console script."""
    import sys

    try:
        cli.main(standalone_mode=False)
    except click.ClickException as e:
        e.show()
        sys.exit(e.exit_code)
    except SystemExit as e:
        sys.exit(e.code if e.code is not None else 0)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
