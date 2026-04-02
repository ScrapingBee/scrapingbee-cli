"""CLI command modules. Register all commands with the main cli group."""

from __future__ import annotations

import click


def register_commands(cli: click.Group) -> None:
    """Register all subcommands with the main cli group."""
    from . import (
        amazon,
        auth,
        chatgpt,
        crawl,
        export,
        fast_search,
        google,
        schedule,
        tutorial,
        usage,
        walmart,
        youtube,
    )

    usage.register(cli)
    auth.register(cli)
    from . import scrape

    scrape.register(cli)
    crawl.register(cli)
    google.register(cli)
    fast_search.register(cli)
    amazon.register(cli)
    walmart.register(cli)
    youtube.register(cli)
    chatgpt.register(cli)
    export.register(cli)
    tutorial.register(cli)
    schedule.register(cli)
    from . import unsafe

    unsafe.register(cli)
