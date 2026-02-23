"""CLI command modules. Register all commands with the main cli group."""

from __future__ import annotations


def register_commands(cli):  # noqa: ANN001
    """Register all subcommands with the main cli group."""
    from . import amazon
    from . import auth
    from . import chatgpt
    from . import crawl
    from . import fast_search
    from . import google
    from . import usage
    from . import walmart
    from . import youtube

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
