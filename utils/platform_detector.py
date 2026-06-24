import re
from urllib.parse import urlparse


# Supported listing platforms -> the domains that identify them.
PLATFORM_DOMAINS = {
    "coinmarketcap": ["coinmarketcap.com"],
    "coingecko": ["coingecko.com"],
    "coinranking": ["coinranking.com"],
}

SUPPORTED_PLATFORMS = list(PLATFORM_DOMAINS.keys())


def _host(url):
    if not url or not isinstance(url, str):
        return ""
    try:
        host = urlparse(url.strip()).netloc.lower()
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def detect_platform(url):
    """Return the platform key for a listing/project URL, or None if unsupported."""
    host = _host(url)
    if not host:
        return None

    for platform, domains in PLATFORM_DOMAINS.items():
        for domain in domains:
            if host == domain or host.endswith("." + domain):
                return platform

    return None


def is_supported(url):
    return detect_platform(url) is not None


def is_category_url(url):
    """True only for a supported platform's category / listing URL.

    Accepts:
    - CoinMarketCap  /cryptocurrency-category/..., /view/..., /coins, etc.
    - CoinGecko      /en/categories/..., /en/coins/..., etc.
    - Coinranking    /coins, /tags, etc.
    Rejects bare homepages and coin-detail pages.
    """
    if not detect_platform(url):
        return False
    try:
        path = urlparse(url.strip()).path.lower().rstrip("/")
    except Exception:
        return False
    if not path:
        return False
    # Reject individual coin pages: /currencies/<slug>, /en/coins/<slug>
    if re.search(r"/(currencies|coins|currency)/[^/]+$", path):
        return False
    return True
