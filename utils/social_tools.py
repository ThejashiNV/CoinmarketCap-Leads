import re
from html import unescape

from utils.url_tools import normalize_url, dedupe_urls


URL_IN_TEXT_REGEX = re.compile(r'https?://[^\s"\'<>)\]]+', re.IGNORECASE)
PROTOCOL_RELATIVE_REGEX = re.compile(r'(?<!:)//[A-Za-z0-9.\-]+\.[A-Za-z]{2,}[^\s"\'<>)\]]*')

LINKEDIN_COMPANY_RE = re.compile(r"linkedin\.com/company/[^/\s?#\"'<>)\]\\]+", re.IGNORECASE)
LINKEDIN_PROFILE_RE = re.compile(r"linkedin\.com/in/[^/\s?#\"'<>)\]\\]+", re.IGNORECASE)
LINKEDIN_SCHOOL_RE = re.compile(r"linkedin\.com/school/[^/\s?#\"'<>)\]\\]+", re.IGNORECASE)

TELEGRAM_RE = re.compile(
    r"(?:t\.me|telegram\.me)/(?!share/|share$)[A-Za-z0-9_+/]+", re.IGNORECASE
)

TWITTER_RE = re.compile(
    r"(?:twitter\.com|x\.com)/(?!share|intent|home|search)[A-Za-z0-9_]+",
    re.IGNORECASE,
)
DISCORD_RE = re.compile(r"(?:discord\.gg|discord\.com/invite)/[A-Za-z0-9\-]+", re.IGNORECASE)
GITHUB_RE = re.compile(r"github\.com/[A-Za-z0-9\-._]+(?:/[A-Za-z0-9\-._]+)?", re.IGNORECASE)

# Aggregator/listing handles that appear on every project page via site chrome.
AGGREGATOR_HANDLES = (
    # Listing / analytics platforms
    "coinmarketcap",
    "coingecko",
    "coinranking",
    "dextools",
    "dexscreener",
    # Exchanges
    "binance",
    "coinbase",
    "kucoin",
    "okx",
    "bybit",
    "gateio",
    "gate_io",
    "mexc",
    "bitget",
    "cryptocom",
    "crypto.com",
    "bitpanda",
    "robinhood",
    # Security / audit platforms
    "certik",
    "immunefi",
    "hackenproof",
    # Crypto news / media (their social handles leak from embedded widgets)
    "coindesk",
    "cointelegraph",
    "decrypt",
    "theblock",
    "bitcoinmagazine",
    "beincrypto",
    # Design / dev tools
    "figma",
    "notion",
)

# Telegram handles that are aggregator/listing noise, not the project's own.
TELEGRAM_BLOCKLIST = (
    *AGGREGATOR_HANDLES,
    "/telegram",
    "share",
    "joinchat/aaaa",
)

GITHUB_BLOCKLIST = (
    # GitHub infrastructure / navigation pages
    "github.com/login",
    "github.com/about",
    "github.com/features",
    "github.com/topics",
    "github.com/sponsors",
    "github.com/marketplace",
    "github.com/pricing",
    "github.com/security",
    "github.com/blog",
    # Generic third-party repos that appear on many crypto project sites
    # (forum software, CMS, UI libraries, etc.)
    "github.com/discourse/discourse",
    "github.com/nicehash/",
    "github.com/nicedoc/",
    "github.com/graphprotocol/graph-node",
)


def _candidate_strings(html):
    """Collect every URL-ish token from anchors and raw text in the HTML."""
    if not html:
        return []
    text = unescape(html)
    tokens = []
    tokens.extend(URL_IN_TEXT_REGEX.findall(text))
    for match in PROTOCOL_RELATIVE_REGEX.findall(text):
        tokens.append("https:" + match)
    return tokens


def _harvest(html, regex):
    text = unescape(html or "")
    hits = set()
    for token in _candidate_strings(html) + [text]:
        for match in regex.findall(token):
            hits.add(match)
    return hits


def extract_linkedin(html):
    raw = (
        _harvest(html, LINKEDIN_COMPANY_RE)
        | _harvest(html, LINKEDIN_PROFILE_RE)
        | _harvest(html, LINKEDIN_SCHOOL_RE)
    )
    urls = []
    for item in raw:
        low = item.lower()
        # Skip aggregator/listing platform LinkedIn pages that leak from site chrome.
        if any(bad in low for bad in AGGREGATOR_HANDLES):
            continue
        norm = normalize_url("https://www." + item if not item.startswith("http") else item)
        if not norm:
            norm = normalize_url("https://" + item)
        if norm and "linkedin.com" in norm:
            urls.append(norm)
    return dedupe_urls(urls)


def extract_telegram(html):
    urls = []
    for item in _harvest(html, TELEGRAM_RE):
        low = item.lower()
        if any(bad in low for bad in TELEGRAM_BLOCKLIST):
            continue
        norm = normalize_url("https://" + item)
        if norm:
            urls.append(norm)
    return dedupe_urls(urls)


def extract_twitter(html):
    urls = []
    for item in _harvest(html, TWITTER_RE):
        low = item.lower()
        # Skip aggregator/listing platform Twitter handles that leak from site chrome.
        if any(bad in low for bad in AGGREGATOR_HANDLES):
            continue
        norm = normalize_url("https://" + item)
        if norm:
            urls.append(norm)
    return dedupe_urls(urls)


def extract_discord(html):
    urls = []
    for item in _harvest(html, DISCORD_RE):
        norm = normalize_url("https://" + item)
        if norm:
            urls.append(norm)
    return dedupe_urls(urls)


def extract_github(html):
    urls = []
    for item in _harvest(html, GITHUB_RE):
        low = item.lower()
        if any(bad in low for bad in GITHUB_BLOCKLIST):
            continue
        norm = normalize_url("https://" + item)
        if norm:
            urls.append(norm)
    return dedupe_urls(urls)


def all_urls(html):
    """Return every absolute http(s) URL found in the HTML, normalized + deduped."""
    return dedupe_urls(_candidate_strings(html))


def extract_socials(html):
    """Extract all social handles from HTML into a dict of de-duplicated lists."""
    return {
        "linkedin": extract_linkedin(html),
        "telegram": extract_telegram(html),
        "twitter": extract_twitter(html),
        "discord": extract_discord(html),
        "github": extract_github(html),
    }
