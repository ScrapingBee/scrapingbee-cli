"""API key and base URL configuration."""

from __future__ import annotations

import os

ENV_API_KEY = "SCRAPINGBEE_API_KEY"
BASE_URL = "https://app.scrapingbee.com/api/v1"


def get_api_key(flag_value: str | None) -> str:
    """Return API key from flag or environment. Raises ValueError if missing."""
    if flag_value:
        return flag_value
    key = os.environ.get(ENV_API_KEY)
    if not key:
        raise ValueError(
            f"API key not provided. Use --api-key flag or set {ENV_API_KEY} environment variable"
        )
    return key
