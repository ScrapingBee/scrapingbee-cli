"""ScrapingBee CLI - Command-line client for the ScrapingBee API."""

import platform
import sys

__version__ = "1.4.0"


def user_agent_headers() -> dict[str, str]:
    """Build structured User-Agent headers for API requests.

    Returns a dict of headers:
        User-Agent: ScrapingBee/CLI
        User-Agent-Client: scrapingbee-cli
        User-Agent-Client-Version: 1.4.0
        User-Agent-Environment: python
        User-Agent-Environment-Version: 3.14.2
        User-Agent-OS: Darwin arm64
    """
    py = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    os_info = f"{platform.system()} {platform.machine()}"
    return {
        "User-Agent": "ScrapingBee/CLI",
        "User-Agent-Client": "scrapingbee-cli",
        "User-Agent-Client-Version": __version__,
        "User-Agent-Environment": "python",
        "User-Agent-Environment-Version": py,
        "User-Agent-OS": os_info,
    }
