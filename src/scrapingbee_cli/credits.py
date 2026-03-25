"""ScrapingBee credit costs per API command.

Exact costs are computed from request parameters when possible.
Estimated ranges are shown as fallback when the ``spb-cost`` response header
is absent (SERP endpoints do not include that header).
"""

from __future__ import annotations

# Fallback ranges — only used when exact cost cannot be determined.
ESTIMATED_CREDITS: dict[str, str] = {
    "google": "10-15",
    "fast-search": "10",
    "amazon-product": "5-15",
    "amazon-search": "5-15",
    "walmart-search": "10-15",
    "walmart-product": "10-15",
    "youtube-search": "5",
    "youtube-metadata": "5",
    "chatgpt": "15",
}


def google_credits(light_request: bool | None = None) -> int:
    """Google Search API: 10 for light requests (default), 15 for regular."""
    if light_request is False:
        return 15
    return 10  # light_request=true is the default


def fast_search_credits() -> int:
    """Fast Search API: always 10 credits."""
    return 10


def amazon_credits(light_request: bool | None = None) -> int:
    """Amazon API: 5 for light requests (default for product), 15 for regular."""
    if light_request is False:
        return 15
    return 5


def walmart_credits(light_request: bool | None = None) -> int:
    """Walmart API: 10 for light requests, 15 for regular."""
    if light_request is False:
        return 15
    return 10


def youtube_credits() -> int:
    """YouTube API: always 5 credits."""
    return 5


def chatgpt_credits() -> int:
    """ChatGPT API: always 15 credits."""
    return 15
