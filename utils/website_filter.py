from urllib.parse import urlparse


BLOCKED_DOMAINS = [
    "certik.com",
    "docs.google.com",
    "drive.google.com",
    "forms.gle",
    "google.com",
    "t.me",
    "telegram.me",
    "medium.com",
    "mirror.xyz",
    "coinmarketcap.com",
    "coingecko.com",
    "coinranking.com",
    "github.com",
    "gitbook.io",
    "notion.site",
    "discord.gg",
    "discord.com",
    "x.com",
    "twitter.com",
    "linkedin.com",
    "youtube.com",
]


def is_valid_website(url):
    """
    Returns True only if the URL appears to be a project's official website.
    """
    if not url or not isinstance(url, str):
        return False

    url = url.strip()

    if not url.startswith(("http://", "https://")):
        return False

    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace("www.", "")
    except Exception:
        return False

    # Block known non-official domains
    for blocked in BLOCKED_DOMAINS:
        if blocked in domain:
            return False

    # Block docs subdomains (docs.project.com is usually documentation, not homepage)
    if domain.startswith("docs."):
        return False

    return True
