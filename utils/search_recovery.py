"""Best-effort LinkedIn / Telegram recovery via public web search.

The enrichment pipeline harvests social links straight from the project's own
pages first. When LinkedIn or Telegram are still missing, this module runs a
*best-effort* web search to recover them (the goal: don't leave a mandatory
field empty if a public profile exists).

Design constraints:
  * Never raise — any network/parse failure returns [] so enrichment continues.
  * Never fabricate: a candidate is only accepted if its slug shares a token
    with the project name or its website/email domain (avoids attaching the
    wrong company's profile to a lead).
  * Light-touch: results are cached per query and engines are tried in order
    with a graceful fallback, so a single run does not hammer any provider.
"""

import logging
import re
import time
from urllib.parse import quote_plus, unquote, urlparse

import requests

from utils.social_tools import extract_linkedin, extract_telegram

logger = logging.getLogger("scraper")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_TIMEOUT = 12
_CACHE = {}

# Generic slug tokens that must not, on their own, qualify a match.
_STOPWORDS = {
    "protocol", "finance", "network", "token", "coin", "crypto", "labs",
    "lab", "official", "global", "foundation", "project", "app", "io",
    "the", "inc", "ltd", "group", "team", "dao", "chain", "defi", "com",
}


def _search_html(query):
    """Return decoded search-results HTML for a query, or "" on any failure."""
    if query in _CACHE:
        return _CACHE[query]

    engines = (
        ("brave", "https://search.brave.com/search?q=" + quote_plus(query)),
        ("ddg", "https://html.duckduckgo.com/html/?q=" + quote_plus(query)),
    )

    result = ""
    for name, url in engines:
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
            if resp.status_code == 429:
                time.sleep(1.5)
                resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
            if resp.status_code == 200 and resp.text:
                result = unquote(resp.text)
                break
        except Exception as exc:  # network errors, timeouts, etc.
            logger.warning("search recovery (%s) failed: %s", name, exc)

    _CACHE[query] = result
    return result


def _tokens(name, website, emails):
    """Significant lowercase tokens drawn from name + website + email domains."""
    tokens = set()

    for word in re.split(r"[^a-z0-9]+", (name or "").lower()):
        if len(word) >= 3 and word not in _STOPWORDS:
            tokens.add(word)

    domains = []
    if website:
        host = urlparse(website if "//" in website else "//" + website).netloc
        if host:
            domains.append(host)
    for email in emails or []:
        if "@" in email:
            domains.append(email.split("@", 1)[1])

    for host in domains:
        host = host.lower().lstrip("www.")
        label = host.split(".")[0] if "." in host else host
        if len(label) >= 3 and label not in _STOPWORDS:
            tokens.add(label)

    return tokens


def _clean_url(url):
    """Drop tracking/query junk so candidate URLs are canonical and dedupable.

    Search-result hrefs often carry suffixes like '&trk=...' or '?fromSignIn=...'
    that survive extraction; strip everything past the first '?', '#' or '&'.
    """
    return re.split(r"[?#&]", url, 1)[0].rstrip("/")


def _slug(url):
    """Trailing path segment of a social URL, lowercased (the handle/company)."""
    return url.rstrip("/").split("/")[-1].lower()


def _rank(candidates, tokens, prefer=("/company/",), limit=2):
    """Keep only token-relevant candidates, best match first (cleaned, capped)."""
    scored = []
    seen = set()
    for raw in candidates:
        url = _clean_url(raw)
        if not url or url in seen:
            continue
        seen.add(url)
        slug = _slug(url)
        slug_words = set(re.split(r"[^a-z0-9]+", slug))
        score = 0
        for tok in tokens:
            if tok in slug_words:
                score += 3          # whole-word token match
            elif tok in slug:
                score += 1          # substring match
        if score == 0:
            continue
        if any(p in url.lower() for p in prefer):
            score += 2
        scored.append((score, -len(slug), url))

    scored.sort(reverse=True)
    ranked = [url for _, _, url in scored]
    return ranked[:limit] if limit else ranked


def recover_linkedin(name, website="", emails=None):
    """Best-effort recovery of a LinkedIn company/profile URL. [] if none safe."""
    tokens = _tokens(name, website, emails)
    if not tokens:
        return []

    query = f"{name} {website} linkedin company".strip()
    html = _search_html(query)
    if not html:
        return []

    candidates = extract_linkedin(html)
    return _rank(candidates, tokens, prefer=("/company/", "/school/"))


def recover_telegram(name, website="", emails=None):
    """Best-effort recovery of a Telegram URL. [] if none safe."""
    tokens = _tokens(name, website, emails)
    if not tokens:
        return []

    query = f"{name} {website} official telegram".strip()
    html = _search_html(query)
    if not html:
        return []

    candidates = extract_telegram(html)
    return _rank(candidates, tokens, prefer=())
