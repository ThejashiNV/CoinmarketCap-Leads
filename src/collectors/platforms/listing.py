import json
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from utils.platform_detector import detect_platform
from utils.text_tools import clean_project_name


PLATFORM_BASE = {
    "coinmarketcap": "https://coinmarketcap.com",
    "coingecko": "https://www.coingecko.com",
    "coinranking": "https://coinranking.com",
}

NEXT_DATA_RE = re.compile(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def _project_slug(platform, path):
    """Return a canonical project path for a project link, or None.

    Each platform exposes per-project pages under a distinct prefix:
      coinmarketcap -> /currencies/<slug>
      coingecko     -> /en/coins/<slug>  (or /coins/<slug>)
      coinranking   -> /coin/<id+slug>
    """
    parts = [p for p in path.strip("/").split("/") if p]

    if platform == "coinmarketcap":
        if len(parts) == 2 and parts[0] == "currencies":
            return f"/currencies/{parts[1]}"

    elif platform == "coingecko":
        if "coins" in parts:
            idx = parts.index("coins")
            if idx + 1 < len(parts):
                slug = parts[idx + 1]
                # Skip category/listing pseudo-pages.
                if slug and slug not in ("recently_added", "high_volume", "categories"):
                    return f"/en/coins/{slug}"

    elif platform == "coinranking":
        if len(parts) >= 2 and parts[0] == "coin":
            return f"/coin/{parts[1]}"

    return None


def name_from_slug(slug_path):
    """Derive a clean display name from a project URL slug.

    Listing-row anchors wrap rank/price/% noise, so the slug is a far more
    reliable name source (e.g. '/currencies/shiba-inu' -> 'Shiba Inu').
    """
    segment = slug_path.rstrip("/").split("/")[-1]
    # Coinranking encodes "<id>+<slug>"; keep the human slug.
    segment = segment.split("+")[-1]
    tokens = [t for t in re.split(r"[-_]", segment) if t]
    if tokens and tokens[-1].isdigit():
        tokens = tokens[:-1]
    return " ".join(tokens).title()


# ---------- CMC structured-data parser for "Recently Added" mode ----------

def _find_crypto_list(node, depth=0):
    """Locate the `cryptoCurrencyList` inside CMC's __NEXT_DATA__.

    This list contains every coin on a category page with full metadata
    including `dateAdded`, `slug`, `name`, `tags`, etc. — richer than
    what the anchor-based parser can extract.
    """
    if depth > 8:
        return None
    if isinstance(node, dict):
        # Direct key match
        candidate = node.get("cryptoCurrencyList")
        if isinstance(candidate, list) and candidate and "slug" in candidate[0]:
            return candidate
        for value in node.values():
            found = _find_crypto_list(value, depth + 1)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_crypto_list(value, depth + 1)
            if found is not None:
                return found
    return None


def _parse_recently_added_cmc(html, listing_url):
    """Parse CMC category page and return projects sorted by dateAdded desc.

    CMC category pages embed a `cryptoCurrencyList` in their __NEXT_DATA__
    JSON blob. Each entry has `slug`, `name`, `dateAdded` (ISO 8601), and
    `tags`. This lets us sort by listing date without any additional HTTP
    requests — the data is already in the page we fetched.
    """
    match = NEXT_DATA_RE.search(html or "")
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except (json.JSONDecodeError, ValueError):
        return None

    coins = _find_crypto_list(data)
    if not coins:
        return None

    base = PLATFORM_BASE["coinmarketcap"]
    projects = []
    for coin in coins:
        slug = coin.get("slug", "")
        name = coin.get("name", "") or name_from_slug(slug)
        date_added = coin.get("dateAdded", "")
        if not slug:
            continue
        projects.append({
            "Project Name": clean_project_name(name) or name,
            "Project URL": f"{base}/currencies/{slug}",
            "Source URL": listing_url,
            "Platform": "coinmarketcap",
            "dateAdded": date_added,
        })

    # Sort by dateAdded descending (newest first)
    projects.sort(key=lambda p: p.get("dateAdded", ""), reverse=True)
    return projects


# ---------- Standard anchor-based parsers (unchanged) ----------

def collect_projects(listing_url, mode="ranked"):
    """Scrape a listing/category page and return [{Project Name, Project URL}].

    mode="ranked"  -> existing behavior: projects in market-cap/rank order.
    mode="recent"  -> new: projects sorted by dateAdded descending (newest first).

    The browser is opened lazily so this module stays importable without a
    running browser (keeps unit tests fast).
    """
    from src.scraping.browser import browser_page, fetch_html

    platform = detect_platform(listing_url)
    if not platform:
        raise ValueError(f"Unsupported platform URL: {listing_url}")

    base = PLATFORM_BASE[platform]

    with browser_page() as page:
        html = fetch_html(page, listing_url, timeout=60000, idle_timeout=6000)

    if mode == "recent" and platform == "coinmarketcap":
        structured = _parse_recently_added_cmc(html, listing_url)
        if structured:
            return structured

    # Default: rank-ordered anchor-based parsing (all platforms)
    return parse_projects(platform, base, html, listing_url)


def _listing_anchors(platform, soup):
    """Anchors that hold the ranked project list for this platform.

    CoinGecko category pages prepend a trending/featured strip *outside* the
    main market table, which corrupts rank order if scanned. Restrict to table
    rows there (falling back to all anchors if no table is present). Other
    platforms (CMC /view/, Coinranking) keep full-document order, which already
    matches their visible ranking.
    """
    if platform == "coingecko":
        table_anchors = []
        for table in soup.find_all("table"):
            table_anchors.extend(table.find_all("a", href=True))
        if table_anchors:
            return table_anchors
    return soup.find_all("a", href=True)


def parse_projects(platform, base, html, listing_url):
    """Pure parsing of listing HTML -> project rows (separated for testing)."""
    soup = BeautifulSoup(html or "", "lxml")

    seen = set()
    projects = []

    for a in _listing_anchors(platform, soup):
        href = a["href"].strip()

        # Resolve to a path on the platform domain only.
        if href.startswith("http"):
            parsed = urlparse(href)
            if detect_platform(href) != platform:
                continue
            path = parsed.path
        elif href.startswith("/"):
            path = href
        else:
            continue

        slug_path = _project_slug(platform, path)
        if not slug_path:
            continue

        project_url = base + slug_path
        if project_url in seen:
            continue
        seen.add(project_url)

        if platform == "coinranking":
            # Coinranking slugs concatenate words ('internetcomputer-icp'); the
            # anchor text is clean ('Internet Computer ICP'). Prefer it and drop
            # the trailing all-caps ticker token.
            raw = re.sub(r"\s+[A-Z0-9]{2,}$", "", a.get_text(" ", strip=True)).strip()
            name = clean_project_name(raw) or name_from_slug(slug_path)
        else:
            name = name_from_slug(slug_path) or clean_project_name(a.get_text(strip=True))

        projects.append(
            {
                "Project Name": name,
                "Project URL": project_url,
                "Source URL": listing_url,
                "Platform": platform,
            }
        )

    return projects
