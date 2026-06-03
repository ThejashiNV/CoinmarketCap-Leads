"""Best-effort LinkedIn / Telegram / Email recovery via public web search.

The enrichment pipeline harvests social links straight from the project's own
pages first. When LinkedIn, Telegram, or Email are still missing, this module
runs a *best-effort* web search to recover them (the goal: don't leave a
mandatory field empty if a public profile or contact address exists).

Design constraints:
  * Never raise — any network/parse failure returns [] so enrichment continues.
  * Never fabricate: a candidate is only accepted if its slug shares a token
    with the project name or its website/email domain (avoids attaching the
    wrong company's profile to a lead).
  * Light-touch: results are cached per query and engines are tried in order
    with a graceful fallback, so a single run does not hammer any provider.
  * Rate-limit aware: engines returning 429/503 are cooled down for 3 minutes.
"""

import logging
import random
import re
import time
from urllib.parse import quote_plus, unquote, urlparse

import requests

from utils.email_tools import extract_emails, _is_clean_email, EMAIL_REGEX
from utils.social_tools import extract_linkedin, extract_telegram

logger = logging.getLogger("scraper")

# Rotate user-agents to reduce fingerprint similarity across a run.
_USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
    "Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
)

_TIMEOUT = 12
_CACHE = {}

# Rate-limit circuit breaker: engine → earliest retry time.
_ENGINE_COOLDOWN = 180  # seconds
_engine_blocked_until = {}  # engine_name → time.time() when cooldown expires

# Global throttle: minimum seconds between search requests.
_MIN_INTERVAL = 2.5
_last_request_time = 0.0

# Round-robin engine rotation index.
_engine_index = 0

# Generic slug tokens that must not, on their own, qualify a match.
_STOPWORDS = {
    "protocol", "finance", "network", "token", "coin", "crypto", "labs",
    "lab", "official", "global", "foundation", "project", "app", "io",
    "the", "inc", "ltd", "group", "team", "dao", "chain", "defi", "com",
}


def _headers():
    """Return request headers with a rotated user-agent."""
    ua = random.choice(_USER_AGENTS)
    return {
        "User-Agent": ua,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml",
    }


def _throttle():
    """Ensure a minimum gap between search requests to avoid burst rate limits."""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < _MIN_INTERVAL:
        jitter = random.uniform(0.3, 1.0)
        time.sleep(_MIN_INTERVAL - elapsed + jitter)
    _last_request_time = time.time()


def _is_engine_available(name):
    """Check if an engine is past its cooldown period."""
    blocked_until = _engine_blocked_until.get(name, 0)
    return time.time() >= blocked_until


def _mark_engine_blocked(name):
    """Mark an engine as rate-limited for the cooldown period."""
    _engine_blocked_until[name] = time.time() + _ENGINE_COOLDOWN
    logger.info("Search engine %s rate-limited, cooling down %ds", name, _ENGINE_COOLDOWN)


def _search_html(query, must_contain=None):
    """Return decoded search-results HTML for a query, or "" on any failure.

    Args:
        query: The search query string.
        must_contain: Optional tuple of substrings. If set, the result HTML
            must contain at least one of them to be accepted (rejects anti-bot
            stub pages that return 200 but have no real results).
    """
    global _engine_index

    cache_key = query
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    all_engines = [
        ("brave", "GET", "https://search.brave.com/search?q=" + quote_plus(query)),
        ("startpage", "GET", "https://www.startpage.com/sp/search?q=" + quote_plus(query)),
        ("yahoo", "GET", "https://search.yahoo.com/search?p=" + quote_plus(query)),
        ("ddg", "POST", "https://html.duckduckgo.com/html/"),
    ]

    # Round-robin: start from a different engine each query to distribute load.
    n = len(all_engines)
    engines = [all_engines[(i + _engine_index) % n] for i in range(n)]
    _engine_index = (_engine_index + 1) % n

    result = ""
    for name, method, url in engines:
        if not _is_engine_available(name):
            continue

        try:
            _throttle()

            if method == "POST":
                resp = requests.post(
                    url,
                    data={"q": query, "b": ""},
                    headers=_headers(),
                    timeout=_TIMEOUT,
                )
            else:
                resp = requests.get(url, headers=_headers(), timeout=_TIMEOUT)

            if resp.status_code in (429, 503):
                _mark_engine_blocked(name)
                continue

            if resp.status_code == 200 and resp.text:
                html = unquote(resp.text)
                # Validate against must_contain if provided.
                if must_contain:
                    if not any(mc in html for mc in must_contain):
                        continue
                result = html
                break
        except Exception as exc:
            logger.warning("search recovery (%s) failed: %s", name, exc)

    _CACHE[cache_key] = result
    return result


def _tokens(name, website, emails):
    """Significant lowercase tokens drawn from name + website + email domains."""
    tokens = set()

    name_lower = (name or "").lower()
    # For short project names (< 5 chars total), allow 2-char tokens.
    min_len = 2 if len(name_lower.replace(" ", "")) < 5 else 3

    for word in re.split(r"[^a-z0-9]+", name_lower):
        if len(word) >= min_len and word not in _STOPWORDS:
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
        if len(label) >= min_len and label not in _STOPWORDS:
            tokens.add(label)

    return tokens


def _clean_url(url):
    """Drop tracking/query junk so candidate URLs are canonical and dedupable.

    Search-result hrefs often carry suffixes like '&trk=...' or '?fromSignIn=...'
    that survive extraction; strip everything past the first '?', '#' or '&'.
    Also strip backslash escapes from JSON-embedded URLs.
    """
    url = url.replace("\\", "")
    # Normalize Telegram /s/ preview URLs → direct URL.
    url = re.sub(r"t\.me/s/", "t.me/", url)
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

    # Try primary query first, then a broader fallback.
    queries = [
        f"{name} {website} linkedin company".strip(),
        f'"{name}" linkedin'.strip(),
    ]

    all_candidates = []
    for query in queries:
        html = _search_html(query, must_contain=("linkedin.com",))
        if html:
            all_candidates.extend(extract_linkedin(html))

    return _rank(all_candidates, tokens, prefer=("/company/", "/school/"))


def recover_telegram(name, website="", emails=None):
    """Best-effort recovery of a Telegram URL. [] if none safe."""
    tokens = _tokens(name, website, emails)
    if not tokens:
        return []

    queries = [
        f"{name} {website} official telegram".strip(),
        f'"{name}" telegram t.me'.strip(),
    ]

    all_candidates = []
    for query in queries:
        html = _search_html(query, must_contain=("t.me/", "telegram.me/"))
        if html:
            all_candidates.extend(extract_telegram(html))

    return _rank(all_candidates, tokens, prefer=())


def _company_from_linkedin(linkedin_urls):
    """Extract the company slug from a LinkedIn URL for query refinement."""
    for url in linkedin_urls or []:
        low = url.lower()
        m = re.search(r"linkedin\.com/company/([^/?#]+)", low)
        if m:
            slug = m.group(1).replace("-", " ")
            return slug
    return ""


def recover_email(name, website="", linkedin_urls=None):
    """Best-effort recovery of official email addresses via web search.

    Only accepts emails on the project's own domain (derived from `website`).
    Returns a list of verified email strings, or [].
    """
    if not website:
        return []

    parsed = urlparse(website if "//" in website else "https://" + website)
    domain = parsed.netloc.lower().lstrip("www.")
    if not domain:
        return []

    # Build search queries.
    queries = [
        f'"{name}" "{domain}" contact email',
    ]

    # If we have a LinkedIn company slug, use it for a refined query.
    company = _company_from_linkedin(linkedin_urls)
    if company and company.lower() != name.lower():
        queries.append(f'"{company}" "{domain}" email')

    # Broader fallback.
    queries.append(f"site:{domain} email contact")

    found = []
    seen = set()

    for query in queries:
        html = _search_html(query, must_contain=(domain, "@"))
        if not html:
            continue

        # Extract all emails from search results HTML.
        candidates = extract_emails(html)
        for email in candidates:
            email_lower = email.lower()
            if email_lower in seen:
                continue
            seen.add(email_lower)

            # Only accept emails on the project's own domain.
            email_domain = email_lower.split("@", 1)[1] if "@" in email_lower else ""
            if email_domain == domain or email_domain.endswith("." + domain):
                found.append(email)

    return found
