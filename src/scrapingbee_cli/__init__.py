"""ScrapingBee CLI - Command-line client for the ScrapingBee API."""

import platform
import sys

__version__ = "1.3.0"


def user_agent() -> str:
    """Build a descriptive User-Agent string for API requests.

    Format: scrapingbee-cli/1.2.3 Python/3.12.0 (Darwin arm64)
    """
    py = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    os_info = f"{platform.system()} {platform.machine()}"
    return f"scrapingbee-cli/{__version__} Python/{py} ({os_info})"
