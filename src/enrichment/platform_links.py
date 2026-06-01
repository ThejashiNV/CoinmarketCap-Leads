import json
import re

from bs4 import BeautifulSoup

from utils.social_tools import extract_socials
from utils.website_validator import is_valid_website, pick_best_website


NEXT_DATA_RE = re.compile(
    r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S
)


def _find_urls_dict(node):
    """Locate the coin's `urls` dict inside a nested Next.js data blob."""
    if isinstance(node, dict):
        candidate = node.get("urls")
        if isinstance(candidate, dict) and (
            "website" in candidate or "twitter" in candidate
        ):
            return candidate
        for value in node.values():
            found = _find_urls_dict(value)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_urls_dict(value)
            if found is not None:
                return found
    return None


def _flatten(urls_dict):
    flat = []
    for value in urls_dict.values():
        if isinstance(value, list):
            flat.extend(str(v) for v in value)
        elif isinstance(value, str):
            flat.append(value)
    return flat


def _from_structured(html):
    """Extract official links from a CMC __NEXT_DATA__ blob, or None."""
    match = NEXT_DATA_RE.search(html or "")
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except (json.JSONDecodeError, ValueError):
        return None

    urls = _find_urls_dict(data)
    if not urls:
        return None

    website = pick_best_website(urls.get("website", []))
    socials = extract_socials(" ".join(_flatten(urls)))
    return website, socials


def _from_dom(html):
    """Anchor-only fallback. Avoids JSON-LD / inline-script noise (schema.org)."""
    soup = BeautifulSoup(html or "", "lxml")
    hrefs = [a["href"].strip() for a in soup.find_all("a", href=True)]
    socials = extract_socials(" ".join(hrefs))
    website = pick_best_website([h for h in hrefs if is_valid_website(h)])
    return website, socials


def extract_platform_links(platform, html):
    """Return (website, socials_dict) for a project page on a given platform.

    CoinMarketCap embeds authoritative official links in a Next.js data blob;
    using it avoids picking up partner/aggregator links scattered in the DOM.
    Other platforms use anchor-only parsing.
    """
    if platform == "coinmarketcap":
        structured = _from_structured(html)
        if structured is not None:
            return structured
    return _from_dom(html)
