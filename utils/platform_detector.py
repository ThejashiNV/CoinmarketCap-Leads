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
    """True only for a supported platform's category listing/index URL.

    Enforces the team rule that extraction starts from a category page
    (e.g. https://coinmarketcap.com/cryptocurrency-category/), never a
    homepage or coin-detail page.
    """
    if not detect_platform(url):
        return False
    try:
        path = urlparse(url.strip()).path.lower()
    except Exception:
        return False
    return "categor" in path
