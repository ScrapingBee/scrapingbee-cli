"""Estimated ScrapingBee credit costs per API command.

These are shown in verbose mode when the ``spb-cost`` response header is absent
(SERP endpoints do not include that header).  Values are taken from the
ScrapingBee documentation.
"""

from __future__ import annotations

# Mapping from CLI command name → estimated credits per request.
# Ranges are expressed as strings (e.g. "10-15") for display purposes.
ESTIMATED_CREDITS: dict[str, str] = {
    "google": "10-15",
    "fast-search": "5",
    "amazon-product": "5-15",
    "amazon-search": "5-15",
    "walmart-search": "10-15",
    "walmart-product": "10-15",
    "youtube-search": "5",
    "youtube-metadata": "5",
    "chatgpt": "15",
}
