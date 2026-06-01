from urllib.parse import urlparse

from utils.url_tools import normalize_url


# Listing/aggregator sites — never a project's official website.
LISTING_DOMAINS = [
    "coinmarketcap.com",
    "coingecko.com",
    "coinranking.com",
    "coinpaprika.com",
    "livecoinwatch.com",
    "nomics.com",
    "cryptocompare.com",
    "messari.io",
    "dexscreener.com",
    "dextools.io",
    "certik.com",
    "certik-skynet.com",
    "skynet.certik.com",
]

# Centralized/decentralized exchanges — not project homepages.
EXCHANGE_DOMAINS = [
    "binance.com",
    "binance.us",
    "coinbase.com",
    "kraken.com",
    "kucoin.com",
    "okx.com",
    "bybit.com",
    "mexc.com",
    "gate.io",
    "huobi.com",
    "htx.com",
    "bitfinex.com",
    "bitget.com",
    "crypto.com",
    "gemini.com",
    "upbit.com",
    "poloniex.com",
    "probit.com",
    "lbank.com",
    "whitebit.com",
    "digifinex.com",
    "ascendex.com",
    "bitmart.com",
    "uniswap.org",
    "pancakeswap.finance",
    # Brokers / affiliate "buy" links that listing sites inject into coin pages.
    "etoro.com",
    "btcc.com",
    "bydfi.com",
    "bingx.com",
    "phemex.com",
    "coinex.com",
    "weex.com",
    "toobit.com",
    "uphold.com",
    "moonpay.com",
    "transak.com",
    "changelly.com",
    "simpleswap.io",
    "changenow.io",
]

# Blockchain explorers — referenced on coin pages but never a project homepage.
EXPLORER_DOMAINS = [
    "etherscan.io",
    "bscscan.com",
    "polygonscan.com",
    "snowtrace.io",
    "arbiscan.io",
    "basescan.org",
    "solscan.io",
    "tronscan.org",
    "blockchair.com",
    "blockchain.com",
    "avax.network",
    "ftmscan.com",
    "celoscan.io",
    "airtable.com",
]

# App stores / extension stores.
APP_STORE_DOMAINS = [
    "apps.apple.com",
    "itunes.apple.com",
    "play.google.com",
    "apps.microsoft.com",
    "chrome.google.com",
    "microsoftedge.microsoft.com",
    "apps.shopify.com",
    "addons.mozilla.org",
]

# Social / community / tooling — captured separately, not "the website".
SOCIAL_TOOL_DOMAINS = [
    "twitter.com",
    "x.com",
    "facebook.com",
    "fb.com",
    "instagram.com",
    "linkedin.com",
    "t.me",
    "telegram.me",
    "telegram.org",
    "discord.gg",
    "discord.com",
    "reddit.com",
    "youtube.com",
    "youtu.be",
    "github.com",
    "gitlab.com",
    "medium.com",
    "mirror.xyz",
    "substack.com",
    "tiktok.com",
    "twitch.tv",
    "linktr.ee",
    "google.com",
    "docs.google.com",
    "drive.google.com",
    "forms.gle",
    "notion.site",
    "gitbook.io",
    "gitbook.com",
]

# Subdomains that indicate docs/blog/support, not the marketing homepage.
NON_HOMEPAGE_SUBDOMAINS = (
    "docs.",
    "doc.",
    "blog.",
    "help.",
    "support.",
    "developer.",
    "developers.",
    "dev.",
    "wiki.",
    "forum.",
    "status.",
    "kb.",
    "faq.",
    "api.",
    "app.",
    "explorer.",
    "rpc.",
    "cdn.",
    "static.",
    "media.",
    "whitepaper.",
)

ASSET_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".webp",
    ".ico",
    ".js",
    ".css",
    ".json",
    ".xml",
    ".pdf",
    ".mp4",
    ".woff",
    ".woff2",
)

# Markup, analytics, CDN and infrastructure domains — never a project site.
INFRA_DOMAINS = [
    "schema.org",
    "w3.org",
    "gmpg.org",
    "googleapis.com",
    "gstatic.com",
    "google-analytics.com",
    "googletagmanager.com",
    "doubleclick.net",
    "jsdelivr.net",
    "unpkg.com",
    "cloudflare.com",
    "cloudflareinsights.com",
    "sentry.io",
    "facebook.net",
    "cloudfront.net",
    "amazonaws.com",
]

_ALL_BLOCKED = (
    LISTING_DOMAINS
    + EXCHANGE_DOMAINS
    + EXPLORER_DOMAINS
    + APP_STORE_DOMAINS
    + SOCIAL_TOOL_DOMAINS
    + INFRA_DOMAINS
)


def _matches(host, domain):
    return host == domain or host.endswith("." + domain)


def is_social_or_tool(url):
    host = _host(url)
    return any(_matches(host, d) for d in SOCIAL_TOOL_DOMAINS)


def _host(url):
    normalized = normalize_url(url)
    if not normalized:
        return ""
    return urlparse(normalized).netloc


def is_valid_website(url):
    """True only if the URL looks like a project's official root website."""
    host = _host(url)
    if not host:
        return False

    if any(_matches(host, d) for d in _ALL_BLOCKED):
        return False

    if host.startswith(NON_HOMEPAGE_SUBDOMAINS):
        return False

    normalized = normalize_url(url)
    if normalized.lower().endswith(ASSET_EXTENSIONS):
        return False

    return True


def pick_best_website(candidates):
    """Choose the most homepage-like URL from candidates.

    Prefers shallower paths (root domain over deep links) among valid sites.
    Returns "" if none qualify.
    """
    valid = [normalize_url(u) for u in candidates if is_valid_website(u)]
    valid = [u for u in valid if u]
    if not valid:
        return ""

    def depth(u):
        path = urlparse(u).path.strip("/")
        return len(path.split("/")) if path else 0

    valid.sort(key=lambda u: (depth(u), len(u)))
    return valid[0]
