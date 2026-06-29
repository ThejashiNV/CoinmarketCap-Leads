"""DeFiLlama Raises collector.

Parses the `__NEXT_DATA__` embedded in https://defillama.com/raises — no
API key required.  Protocol-level links (website, Twitter, GitHub) are
pre-fetched once from https://api.llama.fi/protocols and merged into each
project's ``_seeds`` dict so the enricher can skip the DeFiLlama protocol
page browser-load and jump straight to the project's own website.
"""
import re
import time

import requests

from utils.text_tools import clean_project_name
from utils.url_tools import normalize_url


_RAISES_PAGE   = "https://defillama.com/raises"
_PROTOCOLS_URL = "https://api.llama.fi/protocols"
_BASE          = "https://defillama.com"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*",
}

_JSON_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

_NEXT_DATA_RE = re.compile(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _norm(url):
    if not url:
        return ""
    url = url.strip()
    if url.startswith("//"):
        url = "https:" + url
    if not url.startswith("http"):
        return ""
    return normalize_url(url) or url


def _twitter_url(handle_or_url):
    if not handle_or_url:
        return ""
    h = handle_or_url.strip()
    if h.startswith("http"):
        return _norm(h)
    h = h.lstrip("@").strip()
    if h:
        return _norm(f"https://twitter.com/{h}")
    return ""


def _github_list(raw):
    if not raw:
        return []
    if isinstance(raw, str):
        raw = [raw]
    result = []
    for u in raw:
        n = _norm(u.strip() if isinstance(u, str) else "")
        if n and n not in result:
            result.append(n)
    return result


def _proto_key(defillama_id):
    """Extract the lookup key from a raises defillamaId.

    DeFiLlama raises use two formats:
    - "5892"               → numeric protocol id, used directly as key.
    - "parent#some-slug"   → strip the "parent#" prefix to get a slug key.

    Returns the key string, or "" if input is empty.
    """
    if not defillama_id:
        return ""
    s = defillama_id.strip()
    if s.startswith("parent#"):
        s = s[len("parent#"):]
    return s


# ── Data fetchers ──────────────────────────────────────────────────────────────

def _fetch_raises_from_page():
    """Fetch raises list by parsing __NEXT_DATA__ from defillama.com/raises.

    Returns the raw list of raise dicts (or [] on error).
    No API key required — data is embedded in the page's server-side render.
    """
    try:
        resp = requests.get(_RAISES_PAGE, headers=_HEADERS, timeout=45)
        if resp.status_code != 200:
            return []
        m = _NEXT_DATA_RE.search(resp.text)
        if not m:
            return []
        import json
        nd = json.loads(m.group(1))
        raises = nd.get("props", {}).get("pageProps", {}).get("raises", [])
        return raises if isinstance(raises, list) else []
    except Exception:
        return []


def _fetch_protocols_lookup():
    """Fetch /protocols once and build a combined id+slug keyed lookup.

    DeFiLlama raises use two defillamaId formats:
    - Numeric string (e.g. "5892") → matched by the protocol's ``id`` field.
    - Slug string after stripping "parent#" prefix (e.g. "bracket-protocol") →
      matched by the protocol's ``slug`` field.

    We index each protocol under BOTH its id and slug so a single
    ``lookup.get(key)`` call works regardless of which format the raise uses.
    """
    try:
        resp = requests.get(_PROTOCOLS_URL, headers=_JSON_HEADERS, timeout=30)
        if resp.status_code != 200:
            return {}
        protocols = resp.json()
    except Exception:
        return {}

    lookup = {}
    for p in (protocols or []):
        if not isinstance(p, dict):
            continue

        proto_id   = str(p.get("id") or "").strip()
        proto_slug = (p.get("slug") or "").strip()
        if not proto_id and not proto_slug:
            continue

        website = _norm(p.get("url") or "")
        twitter = _twitter_url(p.get("twitter") or "")
        github  = _github_list(p.get("github") or [])
        desc    = (p.get("description") or "").strip()[:220]
        cat     = (p.get("category") or "").strip()

        entry = {
            "website":     website,
            "twitter":     [twitter] if twitter else [],
            "github":      github,
            "telegram":    [],
            "linkedin":    [],
            "discord":     [],
            "description": desc,
            "proto_cat":   cat,
        }

        if proto_id:
            lookup[proto_id] = entry
        if proto_slug and proto_slug not in lookup:
            lookup[proto_slug] = entry

    return lookup


# ── Category label ─────────────────────────────────────────────────────────────

def _category_label(entry, proto_cat=""):
    """Best human-readable category from a raises entry + optional proto category."""
    # Protocol category from /protocols is most authoritative
    if proto_cat:
        return proto_cat
    cat = (entry.get("category") or "").strip()
    if cat:
        return cat
    cat_group = (entry.get("categoryGroup") or "").strip()
    if cat_group:
        return cat_group
    return (entry.get("round") or "DeFi Raises").strip()


# ── Main collector ─────────────────────────────────────────────────────────────

def fetch_raises(mode="recent"):
    """Fetch DeFiLlama raises and return a list of project dicts.

    mode="recent"  → sorted by raise date descending (newest first)
    mode="ranked"  → sorted by amount raised descending (largest first)

    Raises are sourced from the __NEXT_DATA__ block on defillama.com/raises,
    so no API key is required.

    Protocol-level links (website, Twitter, GitHub) come from api.llama.fi/protocols
    and are stored in the ``_seeds`` dict so the enricher skips the browser-load
    of the DeFiLlama protocol page and jumps straight to website enrichment.

    Raises WITHOUT a defillamaId still appear — they have empty seeds and the
    enricher's search-recovery step will locate their websites by project name.
    """
    # ---- 1. Fetch raises ----
    raises = _fetch_raises_from_page()
    if not raises:
        return []

    # ---- 2. Sort by mode ----
    if mode == "recent":
        raises.sort(key=lambda r: r.get("date") or 0, reverse=True)
    else:
        raises.sort(key=lambda r: (r.get("amount") or 0), reverse=True)

    # ---- 3. Fetch protocol-level links (one batch HTTP call) ----
    proto_lookup = _fetch_protocols_lookup()

    # ---- 4. Build project rows ----
    # Deduplicate by company name — for lead generation one row per company is
    # enough; the most recent (or largest) raise per company is already first
    # after the sort in step 2.
    seen_names = set()
    projects   = []

    for entry in raises:
        raw_name = (entry.get("name") or "").strip()
        name = clean_project_name(raw_name) or raw_name
        if not name:
            continue

        name_key = name.lower()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        # Resolve protocol page URL and matching seeds
        did = (entry.get("defillamaId") or "").strip()
        key = _proto_key(did)

        # Build the DeFiLlama protocol URL.
        # For numeric IDs the page uses the numeric id; for slug-based ids it
        # uses the slug (after stripping the "parent#" prefix).
        # For entries without a defillamaId we create a unique synthetic URL
        # using the name slug so the ResultsStore key is distinct per company.
        if key:
            project_url = f"{_BASE}/protocol/{key}"
        else:
            # Synthetic unique URL — query params survive normalize_url; fragments don't.
            name_slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
            project_url = f"{_RAISES_PAGE}?project={name_slug}"

        proto = proto_lookup.get(key) if key else {}

        # The 'sector' field in raises is actually a free-text description
        raise_desc = (entry.get("sector") or "").strip()[:220]
        proto_desc = (proto or {}).get("description", "")
        description = proto_desc or raise_desc

        seeds = {
            "website":     (proto or {}).get("website", ""),
            "twitter":     list((proto or {}).get("twitter") or []),
            "github":      list((proto or {}).get("github") or []),
            "telegram":    [],
            "linkedin":    [],
            "discord":     [],
            "description": description,
        }

        date_added = ""
        if entry.get("date"):
            date_added = time.strftime(
                "%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(entry["date"])
            )

        projects.append({
            "Project Name": name,
            "Project URL":  project_url,
            "Source URL":   _RAISES_PAGE,
            "Platform":     "defillama",
            "Category":     _category_label(entry, (proto or {}).get("proto_cat", "")),
            "_seeds":       seeds,
            "dateAdded":    date_added,
        })

    return projects
