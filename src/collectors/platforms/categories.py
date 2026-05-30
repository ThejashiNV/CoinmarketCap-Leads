import json
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from src.collectors.platforms.listing import PLATFORM_BASE
from utils.platform_detector import detect_platform


NEXT_DATA_RE = re.compile(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def _category_path(platform, path):
    """Return the canonical category path for a category link, or None.

    Each platform lists its categories under a distinct prefix:
      coinmarketcap -> /cryptocurrency-category/<slug>
      coingecko     -> /en/categories/<slug>
      coinranking   -> /categories/<slug>
    The index page itself (no <slug>) is intentionally rejected.
    """
    parts = [p for p in path.strip("/").split("/") if p]

    if platform == "coinmarketcap":
        if len(parts) == 2 and parts[0] == "cryptocurrency-category":
            return "/" + "/".join(parts)

    elif platform == "coingecko":
        if "categories" in parts:
            idx = parts.index("categories")
            if idx + 1 < len(parts) and parts[idx + 1]:
                return "/" + "/".join(parts)

    elif platform == "coinranking":
        # Coinranking lists each category as /coins/<slug> (e.g. /coins/ai).
        # The all-coins page (/coins) and the favorites view are not categories.
        if len(parts) == 2 and parts[0] == "coins" and parts[1] not in ("favorites",):
            return "/" + "/".join(parts)
        if len(parts) >= 2 and parts[0] in ("categories", "category"):
            return "/" + "/".join(parts)

    return None


def _coinranking_name(text):
    """Coinranking category anchors append a coin count ('AI 1,850')."""
    text = re.sub(r"\s+", " ", (text or "").strip())
    return re.sub(r"\s+[\d,]+$", "", text).strip()


def _name_from_slug(path):
    segment = path.rstrip("/").split("/")[-1]
    tokens = [t for t in re.split(r"[-_]", segment) if t]
    return " ".join(tokens).title()


def _clean_anchor_name(text):
    """Anchor text is the nicest source ('DeFi', 'AI & Big Data') when clean.

    Listing rows sometimes wrap counts/market-cap noise into the same anchor,
    so reject anything long or numeric and fall back to the slug.
    """
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text or len(text) > 40:
        return ""
    if re.search(r"\d", text):
        return ""
    return text


def _from_structured(base, html):
    """Parse CMC categories from the __NEXT_DATA__ blob (props.pageProps.data).

    CMC renders the category list client-side, so the authoritative source is
    the embedded JSON: each entry has a display `name` and a `tagSlugs` slug
    that maps to /cryptocurrency-category/<slug>.
    """
    match = NEXT_DATA_RE.search(html or "")
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
    except (json.JSONDecodeError, ValueError):
        return []

    entries = data.get("props", {}).get("pageProps", {}).get("data")
    if not isinstance(entries, list):
        return []

    seen = set()
    categories = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        slug = (item.get("tagSlugs") or "").split(",")[0].strip()
        if not name or not slug:
            continue
        # CMC serves each category's coin listing at /view/<slug>/; the
        # /cryptocurrency-category/ path is only the category *index*.
        url = f"{base}/view/{slug}/"
        if url in seen:
            continue
        seen.add(url)
        categories.append({"name": name, "url": url})

    categories.sort(key=lambda c: c["name"].lower())
    return categories


def parse_categories(platform, base, html):
    """Pure parsing of a category-index page -> [{name, url}] (testable)."""
    if platform == "coinmarketcap":
        structured = _from_structured(base, html)
        if structured:
            return structured

    soup = BeautifulSoup(html or "", "lxml")

    seen = set()
    categories = []

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()

        if href.startswith("http"):
            if detect_platform(href) != platform:
                continue
            path = urlparse(href).path
        elif href.startswith("/"):
            path = href
        else:
            continue

        cat_path = _category_path(platform, path)
        if not cat_path:
            continue

        url = base + cat_path
        if url in seen:
            continue
        seen.add(url)

        if platform == "coinranking":
            name = _coinranking_name(a.get_text(" ", strip=True)) or _name_from_slug(cat_path)
        else:
            name = _clean_anchor_name(a.get_text(strip=True)) or _name_from_slug(cat_path)

        categories.append({"name": name, "url": url})

    categories.sort(key=lambda c: c["name"].lower())
    return categories


def collect_categories(index_url):
    """Scrape a platform category-index page and return [{name, url}].

    The browser is opened lazily so this module stays importable without a
    running browser.
    """
    from src.scraping.browser import browser_page, fetch_html

    platform = detect_platform(index_url)
    if not platform:
        raise ValueError(f"Unsupported platform URL: {index_url}")

    base = PLATFORM_BASE[platform]

    with browser_page() as page:
        html = fetch_html(page, index_url, timeout=60000, idle_timeout=6000)

    return parse_categories(platform, base, html)
