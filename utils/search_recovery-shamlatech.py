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
import random
import re
import time
from urllib.parse import quote_plus, unquote, urlparse

import requests

from utils.email_tools import extract_emails
from utils.social_tools import extract_linkedin, extract_telegram

logger = logging.getLogger("scraper")

# A small pool of realistic desktop UAs, rotated per request so repeated
# searches in one run don't look like a single hammering client.
_USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
    "Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
)


def _headers():
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        ),
    }


_TIMEOUT = 12
_CACHE = {}

# Public search providers rate-limit bursts (Brave returns HTTP 429 after a
# couple of rapid hits). Space requests out globally and back off on 429 so a
# full multi-lead run keeps recovering instead of tripping a block on lead #3.
_MIN_INTERVAL = 2.5          # minimum seconds between outbound search requests
_last_request_at = [0.0]

# Circuit breaker: once a provider rate-limits us it tends to stay blocked for a
# while, so skip it for a cooldown window instead of paying the full backoff on
# every subsequent lookup in the same run.
_ENGINE_COOLDOWN = 180.0     # seconds an engine stays disabled after a 429/503
_engine_blocked_until = {}


def _throttle():
    """Block until at least _MIN_INTERVAL has elapsed since the last request."""
    elapsed = time.time() - _last_request_at[0]
    wait = _MIN_INTERVAL - elapsed
    if wait > 0:
        time.sleep(wait + random.uniform(0, 0.7))
    _last_request_at[0] = time.time()

# Generic slug tokens that must not, on their own, qualify a match.
_STOPWORDS = {
    "protocol", "finance", "network", "token", "coin", "crypto", "labs",
    "lab", "official", "global", "foundation", "project", "app", "io",
    "the", "inc", "ltd", "group", "team", "dao", "chain", "defi", "com",
}


def _fetch(name, method, url, data=None):
    """One throttled request with exponential backoff on rate-limit (429).

    Returns decoded HTML on success or "" on failure. `unquote` is applied so
    that engines which wrap result links in encoded redirects (e.g. DuckDuckGo's
    'uddg=' parameter) expose the real target URL to the extractors.
    """
    backoffs = (0, 4, 9)  # first try immediate; then wait out a 429 block
    for attempt, pause in enumerate(backoffs):
        if pause:
            time.sleep(pause + random.uniform(0, 1.5))
        _throttle()
        try:
            if method == "POST":
                resp = requests.post(
                    url, data=data, headers=_headers(), timeout=_TIMEOUT
                )
            else:
                resp = requests.get(url, headers=_headers(), timeout=_TIMEOUT)
        except Exception as exc:  # network errors, timeouts, etc.
            logger.warning("search recovery (%s) failed: %s", name, exc)
            return ""

        if resp.status_code in (429, 503):
            if attempt < len(backoffs) - 1:
                logger.info("search recovery (%s) rate-limited; backing off", name)
                continue
            # Persistently blocked: trip the breaker so we stop wasting backoff
            # time on this provider for the rest of the run.
            _engine_blocked_until[name] = time.time() + _ENGINE_COOLDOWN
            logger.info("search recovery (%s) blocked; skipping for %ds", name, int(_ENGINE_COOLDOWN))
            return ""
        if resp.status_code == 200 and resp.text:
            return unquote(resp.text)
        return ""
    return ""


def _search_html(query, must_contain=("linkedin.com", "t.me/")):
    """Return decoded search-results HTML for a query, or "" on any failure.

    Tries providers in order and returns the first whose HTML contains any of
    `must_contain` (a relevance gate that rejects anti-bot stubs). The default
    keeps the existing LinkedIn/Telegram behaviour unchanged; email recovery
    passes the project's own domain so it only accepts a relevant results page.
    Results are cached per (query, gate) so a single run never re-hits a
    provider for the same lookup.
    """
    cache_key = (query, must_contain)
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    q = quote_plus(query)
    # Provider order is a reliability ranking learned empirically: Brave exposes
    # the cleanest result links but rate-limits bursts (HTTP 429); Startpage and
    # Yahoo are slower but tolerate sustained use and surface the same LinkedIn /
    # Telegram links, so they cover Brave's gaps during a large run. DuckDuckGo's
    # HTML endpoint serves an anti-bot stub (202, no results) and is a last-ditch.
    engines = (
        ("brave", "GET", "https://search.brave.com/search?q=" + q, None),
        ("startpage", "GET", "https://www.startpage.com/sp/search?query=" + q, None),
        ("yahoo", "GET", "https://search.yahoo.com/search?p=" + q, None),
        ("ddg", "POST", "https://html.duckduckgo.com/html/", {"q": query}),
    )

    result = ""
    for name, method, url, data in engines:
        if time.time() < _engine_blocked_until.get(name, 0):
            continue  # provider is in its post-429 cooldown window
        html = _fetch(name, method, url, data)
        if html and any(marker in html for marker in must_contain):
            result = html
            break

    _CACHE[cache_key] = result
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
    and escaped slashes ('foo\\') that survive extraction; strip everything past
    the first query/fragment/escape char and trailing path punctuation. Telegram
    web-preview links ('t.me/s/<chan>') are normalized to their plain form so
    they dedupe against the canonical channel URL.
    """
    url = re.split(r"[?#&\\]", url, 1)[0].rstrip("/\\")
    url = re.sub(r"(t\.me|telegram\.me)/s/", r"\1/", url, flags=re.I)
    return url


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


def _domain(website):
    """Bare host (no scheme, no www) for a website URL, or "" if unusable."""
    if not website:
        return ""
    host = urlparse(website if "//" in website else "//" + website).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _company_from_linkedin(linkedin_urls):
    """Derive a human company identity from a LinkedIn company/school slug.

    'linkedin.com/company/allora-labs' -> 'allora labs'. Returns "" if no
    company/school URL is present (personal /in/ profiles are ignored).
    """
    for url in linkedin_urls or []:
        match = re.search(r"linkedin\.com/(?:company|school)/([^/?#]+)", url.lower())
        if match:
            return match.group(1).replace("-", " ").replace("_", " ").strip()
    return ""


def recover_email(name, website="", linkedin_urls=None):
    """Best-effort recovery of a business email, conservatively.

    Only used as a last resort when the website crawl found no email but a
    LinkedIn identity exists. Searches using the project name + website domain +
    LinkedIn company identity, then accepts ONLY addresses that actually appear
    in the results AND sit on the project's own domain. Never guesses or
    constructs an address from a pattern, so it cannot fabricate a lead.
    """
    domain = _domain(website)
    if not domain:
        return []

    company = _company_from_linkedin(linkedin_urls)
    queries = [f"{name} {domain} contact email"]
    if company and company not in (name or "").lower():
        queries.append(f"{company} {domain} email")

    found = []
    for query in queries:
        query = query.strip()
        html = _search_html(query, must_contain=(domain,))
        if not html:
            continue
        # Guard against a search engine echoing our query back as text (which
        # could surface a bogus "<query>@domain" address). Reject anything that
        # looks reflected or uses plus-addressing.
        query_blob = query.lower().replace(" ", "")
        for email in extract_emails(html):
            local, _, email_domain = email.partition("@")
            email_domain = email_domain.lower()
            if email_domain != domain and not email_domain.endswith("." + domain):
                continue
            if "+" in local or local in query_blob:
                continue
            if email not in found:
                found.append(email)
        if found:
            break
    return found
