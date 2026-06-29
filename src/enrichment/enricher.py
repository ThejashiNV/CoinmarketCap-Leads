import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from src.scraping.browser import fetch_html
from src.enrichment.platform_links import extract_platform_links
from src.enrichment.store import NA
from utils.email_tools import (
    extract_emails,
    join_business_emails,
    choose_business_emails,
    has_quality_email,
)
from utils.search_recovery import (
    recover_linkedin, recover_telegram, recover_email,
    recover_github, recover_founder_linkedin, recover_founder_search,
    recover_website,
)
from utils.social_tools import extract_socials, all_urls
from utils.text_tools import clean_project_name
from utils.url_tools import normalize_url, root_domain_url, join_urls, host_of
from utils.website_validator import is_valid_website, is_social_or_tool


logger = logging.getLogger("scraper")

_NEXT_DATA_RE = re.compile(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_MAX_DESC_LEN = 220


def _extract_description(html, max_len=_MAX_DESC_LEN):
    """Return a short description from HTML meta tags (og:description or description)."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    for attrs in (
        {"property": "og:description"},
        {"name": "description"},
        {"name": "twitter:description"},
    ):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content", "").strip():
            return tag["content"].strip()[:max_len]
    return ""


def _extract_nextdata_description(html, max_len=_MAX_DESC_LEN):
    """Pull description out of a CMC/CoinGecko __NEXT_DATA__ JSON blob."""
    m = _NEXT_DATA_RE.search(html or "")
    if not m:
        return ""
    try:
        data = json.loads(m.group(1))
    except Exception:
        return ""

    def _search(node, depth=0):
        if depth > 12:
            return ""
        if isinstance(node, dict):
            v = node.get("description", "")
            if isinstance(v, str) and len(v) > 30:
                return v[:max_len]
            for child in node.values():
                result = _search(child, depth + 1)
                if result:
                    return result
        elif isinstance(node, list):
            for item in node:
                result = _search(item, depth + 1)
                if result:
                    return result
        return ""

    return _search(data)


# ── Founder extraction ────────────────────────────────────────────────────────

_FOUNDER_TITLE_RE = re.compile(
    r'\b(founder|co[- ]?founder|ceo|chief\s+executive|president|'
    r'managing\s+director|cto|coo|cfo|cpo|general\s+partner|'
    r'chief\s+(?:technology|operating|financial|product|growth|'
    r'marketing|revenue|people|strategy)\s+officer)\b',
    re.IGNORECASE,
)

_PERSON_NAME_RE = re.compile(
    r'\b([A-Z][a-záéíóúàèùâêîôûäëïöüñç\'-]+'
    r'(?:\s+[A-Z][a-záéíóúàèùâêîôûäëïöüñç\'-]+){1,2})\b'
)

_NAME_SKIP = frozenset({
    "linkedin", "twitter", "github", "telegram", "discord", "youtube",
    "facebook", "instagram", "medium", "reddit", "official", "website",
    "contact", "about", "team", "company", "follow", "view", "join",
    "download", "learn", "read", "click", "visit", "get", "see",
    "build", "create", "launch", "start", "our", "the", "new", "all",
    # Common crypto/tech project suffixes that look like name words.
    "bot", "labs", "protocol", "network", "foundation", "dao",
    "defi", "blockchain", "crypto", "token", "chain", "finance",
    "financial", "capital", "ventures", "web3", "admin", "press", "news",
    "global", "international", "digital", "virtual", "decentralized",
    "autonomous", "collective", "alliance", "exchange", "asset", "fund",
    "group", "holdings", "systems", "services", "solutions",
})

# Pages most likely to contain founder/team information.
_FOUNDER_PATH_KEYWORDS = (
    "/team", "/about", "/about-us", "/our-team", "/people", "/leadership",
    "/founders", "/founder", "/management", "/company", "/our-story",
)


# Words that look Title-case but are titles, not name components.
# Used to strip trailing title words from greedy regex matches like "Marvin Tong Co-founder".
_TITLE_WORDS = frozenset({
    "co-founder", "cofounder", "founder", "founders",
    "ceo", "cto", "coo", "cfo", "cpo", "cmo",
    "president", "director", "officer", "manager",
    "chairman", "chairwoman", "partner", "principal",
    "engineer", "developer", "advisor", "adviser", "head", "vp",
})


def _strip_title_suffix(name):
    """Remove trailing title-word components that crept into a regex match.

    e.g. 'Marvin Tong Co-founder' → 'Marvin Tong'
    """
    words = name.split()
    while words and words[-1].lower().strip("-&,") in _TITLE_WORDS:
        words.pop()
    return " ".join(words).strip()


def _has_vowel(word):
    """Return True if word contains at least one vowel (filters abbreviations like 'Dfns')."""
    return any(c in "aeiouyáéíóúàèùâêîôûäëïöü" for c in word.lower())


def _extract_person_name(text, max_len=50):
    """Return the first plausible personal name from text, or '' if none found."""
    for m in _PERSON_NAME_RE.findall(text or ""):
        m = _strip_title_suffix(m)
        words = m.split()
        if not (2 <= len(words) <= 3):
            continue
        if len(m) > max_len:
            continue
        if any(s in m.lower() for s in _NAME_SKIP):
            continue
        if not all(_has_vowel(w) for w in words):
            continue
        if all(w[0].isupper() and not w.isupper() for w in words):
            return m
    return ""


def _extract_founders(pages_html):
    """Extract (founder_name, founder_linkedin) from a list of HTML pages.

    Priority (score):
      10 — JSON-LD Organization.founder field
       9 — JSON-LD Person @type with founder job title
       8 — meta author tag (only on pages whose URL suggests team/about)
       7 — "Founded by Name" / "Name, Co-Founder" plain-text patterns
       6 — LinkedIn /in/ link with founder-title in surrounding context
       4 — CSS-class team card containing founder title

    Returns ("", "") when nothing reliable is found.
    """
    candidates = []  # (name, linkedin_url, score)

    for html in pages_html:
        if not html or len(html) < 200:
            continue
        soup = BeautifulSoup(html, "lxml")

        # ---- 1. JSON-LD ----
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                raw = script.string or script.get_text()
                data = json.loads(raw)
            except Exception:
                continue

            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue

                # Organization / WebSite with explicit founder field
                for role_key in ("founder", "founders"):
                    role_val = item.get(role_key)
                    if not role_val:
                        continue
                    persons = role_val if isinstance(role_val, list) else [role_val]
                    for person in persons:
                        if not isinstance(person, dict):
                            continue
                        raw_fn = person.get("name", "").strip()
                        if not raw_fn:
                            continue
                        # Validate: must look like a real personal name
                        fn = _extract_person_name(raw_fn) or (
                            raw_fn if (
                                2 <= len(raw_fn.split()) <= 3
                                and all(w[0].isupper() and _has_vowel(w) for w in raw_fn.split())
                                and not any(s in raw_fn.lower() for s in _NAME_SKIP)
                            ) else ""
                        )
                        if not fn:
                            continue
                        same_as = person.get("sameAs", [])
                        if isinstance(same_as, str):
                            same_as = [same_as]
                        url_val = person.get("url", "")
                        all_u = list(same_as) + ([url_val] if url_val else [])
                        fl = next(
                            (u for u in all_u if "linkedin.com/in/" in u.lower()), ""
                        )
                        candidates.append((fn, fl, 10))

                # Standalone Person node with a founder job title
                if item.get("@type") == "Person":
                    job = item.get("jobTitle", "") or item.get("roleName", "")
                    if not _FOUNDER_TITLE_RE.search(job):
                        continue
                    raw_fn = item.get("name", "").strip()
                    if not raw_fn:
                        continue
                    fn = _extract_person_name(raw_fn) or (
                        raw_fn if (
                            2 <= len(raw_fn.split()) <= 3
                            and all(w[0].isupper() and _has_vowel(w) for w in raw_fn.split())
                            and not any(s in raw_fn.lower() for s in _NAME_SKIP)
                        ) else ""
                    )
                    if not fn:
                        continue
                    same_as = item.get("sameAs", [])
                    if isinstance(same_as, str):
                        same_as = [same_as]
                    url_val = item.get("url", "")
                    all_u = list(same_as) + ([url_val] if url_val else [])
                    fl = next(
                        (u for u in all_u if "linkedin.com" in u.lower()), ""
                    )
                    candidates.append((fn, fl, 9))

        # ---- 2. meta author tag ----
        for attrs in ({"name": "author"}, {"property": "article:author"}):
            tag = soup.find("meta", attrs=attrs)
            if tag:
                raw_fn = tag.get("content", "").strip()
                fn = _extract_person_name(raw_fn)
                if fn:
                    candidates.append((fn, "", 8))

        # ---- 3. Plain-text "Founded by X" pattern ----
        page_text = soup.get_text(" ", strip=True)
        for m in _FOUNDED_BY_RE.finditer(page_text):
            fn = m.group(1).strip()
            if fn and _extract_person_name(fn):
                candidates.append((fn, "", 7))

        # ---- 4. "Name, Founder/CEO" pattern ----
        for m in _NAME_COMMA_TITLE_RE.finditer(page_text):
            fn = m.group(1).strip()
            clean = _extract_person_name(fn)
            if clean:
                candidates.append((clean, "", 7))

        # ---- 5. LinkedIn /in/ links near founder-title text ----
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if "linkedin.com/in/" not in href.lower():
                continue
            # Walk up 3 ancestors to collect surrounding context
            context_parts = [a.get_text(" ", strip=True)]
            parent = a.parent
            for _ in range(3):
                if parent is None:
                    break
                chunk = parent.get_text(" ", strip=True)
                if len(chunk) <= 600:
                    context_parts.append(chunk)
                parent = parent.parent
            context = " ".join(context_parts)
            if not _FOUNDER_TITLE_RE.search(context):
                continue
            fn = _extract_person_name(context)
            if fn:
                li_clean = re.split(r"[?#&]", href)[0].rstrip("/")
                candidates.append((fn, li_clean, 6))

        # ---- 6. Team / leadership card sections ----
        CARD_KW = ("team", "founder", "leader", "person", "member",
                   "people", "staff", "executive", "management", "bio",
                   "profile", "advisor", "adviser")
        for section in soup.find_all(["div", "article", "li", "section"]):
            cls = " ".join(section.get("class") or []).lower()
            data_attrs = " ".join(str(v) for v in section.attrs.values()).lower()
            if not any(kw in cls or kw in data_attrs for kw in CARD_KW):
                continue
            text = section.get_text(" ", strip=True)
            if not _FOUNDER_TITLE_RE.search(text):
                continue
            if len(text) > 800:
                continue
            fn = _extract_person_name(text)
            if not fn:
                # Try "Name, Title" pattern inside the card
                for m in _NAME_COMMA_TITLE_RE.finditer(text):
                    fn = _extract_person_name(m.group(1))
                    if fn:
                        break
            if not fn:
                continue
            li_url = ""
            for a in section.find_all("a", href=True):
                if "linkedin.com/in/" in a.get("href", "").lower():
                    li_url = re.split(r"[?#&]", a["href"])[0].rstrip("/")
                    break
            candidates.append((fn, li_url, 4))

    if not candidates:
        return "", ""

    # Highest score wins; break ties by preferring candidates with a LinkedIn URL
    candidates.sort(key=lambda x: (x[2], bool(x[1])), reverse=True)
    best_name, best_li, _ = candidates[0]

    best_name = best_name.strip()
    if best_li and "linkedin.com" in best_li:
        if not best_li.startswith("http"):
            best_li = "https://" + best_li
        best_li = re.split(r"[?#&]", best_li)[0].rstrip("/")
    else:
        best_li = ""

    return best_name, best_li


# Plain-text founder patterns — checked on ALL pages (lower scores than structured data).
_FOUNDED_BY_RE = re.compile(
    r'(?:founded|co[- ]?founded|created|built|started)\s+by\s+'
    r'([A-Z][a-záéíóúàèùâêîôûäëïöüñç\'-]+(?:\s+[A-Z][a-záéíóúàèùâêîôûäëïöüñç\'-]+){1,2})',
    re.IGNORECASE,
)

_NAME_COMMA_TITLE_RE = re.compile(
    r'([A-Z][a-záéíóúàèùâêîôûäëïöüñç\'-]+(?:\s+[A-Z][a-záéíóúàèùâêîôûäëïöüñç\'-]+){1,2})'
    r'\s*[,–—]\s*(?:Co[-\s]?)?(?:Founder|CEO|Chief\s+Executive|President|Managing\s+Director)',
    re.IGNORECASE,
)

_AUTHOR_META_RE = re.compile(r'<meta[^>]+name=["\']author["\'][^>]+content=["\']([^"\']+)["\']', re.IGNORECASE)


def _extract_footer_emails(html):
    """Return emails found specifically inside footer elements.

    Footer emails are high-value — companies often put official contact
    addresses there rather than on a dedicated /contact page.
    """
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    footer_html_parts = []

    # Semantic footer tag
    for el in soup.find_all("footer"):
        footer_html_parts.append(str(el))

    # Elements whose id or class suggests they are a footer
    FOOTER_KEYWORDS = ("footer", "foot", "bottom", "site-info")
    for el in soup.find_all(["div", "section", "nav", "aside"], id=True):
        if any(kw in (el.get("id") or "").lower() for kw in FOOTER_KEYWORDS):
            footer_html_parts.append(str(el))
    for el in soup.find_all(["div", "section", "nav", "aside"]):
        cls = " ".join(el.get("class") or []).lower()
        if any(kw in cls for kw in FOOTER_KEYWORDS):
            footer_html_parts.append(str(el))

    if not footer_html_parts:
        return []

    combined = " ".join(footer_html_parts)
    from utils.email_tools import extract_emails
    return extract_emails(combined)


_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Standard contact/info paths crawled on every official website.
# Fetched concurrently via plain HTTP (no browser) so adding more paths
# costs very little wall-clock time.
CONTACT_PATHS = [
    # Direct contact / about
    "/contact",
    "/contact-us",
    "/about",
    "/about-us",
    # Team / people / leadership — high value for founder extraction
    "/team",
    "/our-team",
    "/our-story",
    "/get-in-touch",
    "/people",
    "/leadership",
    "/founders",
    "/founder",
    "/management",
    # Company info
    "/company",
    "/community",
    "/support",
    "/careers",
    "/jobs",
    "/press",
    "/terms",
    # High-value email discovery paths
    "/foundation",
    "/media",
    "/media-kit",
    "/press-kit",
    "/newsroom",
    "/partners",
    "/partner",
    "/ecosystem",
    "/grants",
    "/collaborate",
    "/work-with-us",
    # Privacy/legal — crawled for social links, emails hard-filtered at extraction
    "/privacy",
    "/privacy-policy",
]

# Contact-related keywords used to discover internal links from the homepage.
_CONTACT_LINK_RE = re.compile(
    r"\b(contact|about|team|company|support|press|media|community|"
    r"partners?|foundation|careers?|jobs?|impressum|imprint|"
    r"people|leadership|founders?|management|our[- ]team|our[- ]story|get[- ]in[- ]touch)\b",
    re.IGNORECASE,
)
# File extensions that are never contact pages.
_NON_PAGE_SUFFIXES = (
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico",
    ".pdf", ".zip", ".mp4", ".mp3", ".css", ".js", ".json", ".xml",
    ".woff", ".woff2", ".ttf", ".eot",
)

# Priority contact paths for browser fallback (only rendered when static fails).
_BROWSER_FALLBACK_PATHS = ("/contact", "/contact-us", "/about", "/about-us", "/team")

SOCIAL_KEYS = ["linkedin", "telegram", "twitter", "discord", "github"]


def _new_accumulator():
    acc = {"emails": []}
    for key in SOCIAL_KEYS:
        acc[key] = []
    return acc


def _merge(acc, emails, socials):
    for email in emails:
        if email not in acc["emails"]:
            acc["emails"].append(email)
    for key in SOCIAL_KEYS:
        for url in socials.get(key, []):
            if url not in acc[key]:
                acc[key].append(url)


def harvest(html):
    """Pull emails, socials, and candidate websites out of one page's HTML."""
    emails = extract_emails(html)
    socials = extract_socials(html)
    websites = [u for u in all_urls(html) if is_valid_website(u)]
    return emails, socials, websites


def _needs_socials(acc):
    """True while LinkedIn or Telegram is still missing."""
    return not (acc["linkedin"] and acc["telegram"])


def _needs_more(acc):
    """True while any mandatory field is still empty (email OR socials)."""
    return not (acc["emails"] and acc["linkedin"] and acc["telegram"])


def _refine_name(html, fallback_name, website):
    if fallback_name:
        return fallback_name
    soup = BeautifulSoup(html or "", "lxml")
    title = soup.title.get_text(strip=True) if soup.title else ""
    if title:
        name = re.split(r"[|\-–—:]", title)[0].strip()
        name = clean_project_name(name)
        if name:
            return name
    if website:
        host = normalize_url(website).split("//")[-1]
        return host.split(".")[0].capitalize()
    return fallback_name or "Unknown"


def _fetch_static(url, timeout=8):
    """Fast HTTP GET for static pages (no JS rendering). Returns HTML or ''."""
    try:
        resp = requests.get(url, headers=_HTTP_HEADERS, timeout=timeout,
                            allow_redirects=True)
        if resp.status_code == 200 and resp.text:
            return resp.text
    except requests.RequestException:
        pass
    return ""


def _fetch_batch(urls, max_workers=8, timeout=8):
    """Fetch multiple URLs concurrently via plain HTTP. Returns {url: html}."""
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch_static, url, timeout): url for url in urls}
        for future in as_completed(futures):
            url = futures[future]
            try:
                results[url] = future.result()
            except Exception:
                results[url] = ""
    return results


def _discover_contact_links(home_html, root):
    """Parse homepage anchors for internal links that look like contact/about pages.

    Returns up to 8 absolute same-domain URLs not already in CONTACT_PATHS.
    This catches non-standard paths like /get-in-touch, /our-team, /newsroom/contact.
    """
    if not home_html or not root:
        return []

    root_host = urlparse(root).netloc.lower()
    known_paths = {p.lstrip("/").lower() for p in CONTACT_PATHS}
    soup = BeautifulSoup(home_html, "lxml")
    found = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(strip=True).lower()

        # Only consider internal links.
        if href.startswith("/"):
            full = urljoin(root + "/", href.lstrip("/"))
        elif href.startswith(("http://", "https://")):
            if urlparse(href).netloc.lower().lstrip("www.") != root_host.lstrip("www."):
                continue
            full = href
        else:
            continue

        # Skip non-page resources.
        low_href = href.lower()
        if low_href.endswith(_NON_PAGE_SUFFIXES):
            continue

        # Skip if it's already a known CONTACT_PATHS entry.
        path = urlparse(full).path.strip("/").lower()
        if path in known_paths or not path:
            continue

        # Match by link text or href against contact keywords.
        if not _CONTACT_LINK_RE.search(text) and not _CONTACT_LINK_RE.search(low_href):
            continue

        norm = normalize_url(full)
        if norm and norm not in seen:
            seen.add(norm)
            found.append(norm)

        if len(found) >= 8:
            break

    return found


def _secondary_domains(home_html, primary_root, project_name=""):
    """Discover secondary official domains linked from the homepage.

    Many crypto projects have a separate foundation/organization site
    (e.g. cardano.org → cardanofoundation.org). Mining those domains
    surfaces contact emails that the primary site doesn't publish.

    Returns up to 2 unique secondary domain roots (scheme://host), filtered
    to exclude known aggregators, social platforms, and exchanges. Crucially,
    secondary domains must share at least one token with the primary domain's
    SLD or project name — this prevents picking up unrelated third-party sites
    that happen to appear in footers (e.g. license pages, job boards).
    """
    if not home_html or not primary_root:
        return []

    primary_host = urlparse(primary_root).netloc.lower().lstrip("www.")
    # Significant tokens from the primary domain (e.g. "bitcoin", "ethereum")
    primary_sld = primary_host.split(".")[0]
    # Additional tokens from project name
    name_tokens = set(
        w for w in re.split(r"[^a-z0-9]+", (project_name or "").lower())
        if len(w) >= 4
    )
    relevance_tokens = {primary_sld} | name_tokens

    soup = BeautifulSoup(home_html, "lxml")
    found = {}

    _GENERIC_SKIP = (
        "meetup.com", "stackexchange.com", "stackoverflow.com",
        "eventbrite.com", "lu.ma", "luma.com", "typeform.com",
        "notion.so", "airtable.com", "lever.co", "greenhouse.io",
        "bamboohr.com", "workable.com", "jobs.com",
    )

    def _check_and_add(host, context_text=""):
        """Apply all filters and add host to found if it passes."""
        if not host or host == primary_host or host in found:
            return
        if is_social_or_tool(f"https://{host}"):
            return
        if not is_valid_website(f"https://{host}"):
            return
        if any(host.endswith(g) for g in _GENERIC_SKIP):
            return
        # Relevance: host or surrounding text must contain a project token.
        combined = (host + " " + context_text).lower()
        if not any(tok in combined for tok in relevance_tokens if len(tok) >= 4):
            return
        found[host] = f"https://{host}"

    # Pass 1: parsed <a> tags (covers normal visible links)
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href.startswith("http"):
            continue
        host = urlparse(href).netloc.lower().lstrip("www.")
        _check_and_add(host, a.get_text(" ", strip=True) + " " + href)

    # Pass 2: raw-text href scan (catches links inside HTML comments, e.g.
    # bitcoin.org's footer links bitcoinfoundation.org inside <!-- --> which
    # BeautifulSoup skips)
    if len(found) < 2:
        for match in re.findall(r'href=["\']?(https?://[^"\'\s>]+)', home_html):
            host = urlparse(match).netloc.lower().lstrip("www.")
            _check_and_add(host, match)
            if len(found) >= 2:
                break

    return list(found.values())


def enrich_project(page, project):
    """Run the multi-source fallback pipeline for a single project."""
    project_url = project["Project URL"]
    platform = project.get("Platform", "")
    source_url = project.get("Source URL", "")
    category = project.get("Category", "")
    name = clean_project_name(project.get("Project Name", ""))

    acc = _new_accumulator()
    website = ""
    email_source = None
    contact_page_url = ""

    def note_email_source(stage, url=""):
        nonlocal email_source, contact_page_url
        if email_source is None and acc["emails"]:
            email_source = stage
            if url and not contact_page_url:
                contact_page_url = url

    # ---- STEP 0: pre-seed from collector (DeFiLlama and future API-first platforms) ----
    # When the collector already knows the website and social URLs (e.g. from the
    # DeFiLlama Raises API), skip the platform page browser-load entirely and
    # pre-populate the accumulator from the supplied seed dict.  All subsequent
    # enrichment steps (website crawl, contact pages, search recovery) run normally.
    t_start = time.time()  # total-timer reference
    seeds = project.get("_seeds") or {}
    html = ""
    t_platform = 0.0

    if seeds:
        website = normalize_url(seeds.get("website", "")) or seeds.get("website", "")
        for key in SOCIAL_KEYS:
            for u in (seeds.get(key) or []):
                u_norm = normalize_url(u) if u else ""
                if u_norm and u_norm not in acc[key]:
                    acc[key].append(u_norm)
    else:
        # ---- STEP 1: platform project page (authoritative structured links) ----
        t0 = time.time()
        html = fetch_html(page, project_url, timeout=25000, idle_timeout=3000)
        website, socials = extract_platform_links(platform, html)
        _merge(acc, [], socials)
        name = _refine_name(html, name, website)
        t_platform = time.time() - t0

    # ---- STEP 2: official website homepage ----
    t1 = time.time()
    home_html = ""
    if website:
        root = root_domain_url(website)
        home_html = fetch_html(page, website, timeout=20000, idle_timeout=2500)
        emails, socials, _ = harvest(home_html)
        _merge(acc, emails, socials)
        footer_emails = _extract_footer_emails(home_html)
        _merge(acc, footer_emails, {})
        note_email_source("Website", website)
    t_website = time.time() - t1

    # ---- STEP 2.5: website search recovery ----
    # When no website was found from seeds, platform page, or homepage crawl,
    # search public web results for the official site by project name.
    # This primarily benefits DeFiLlama raises without a matched protocol page.
    t_website_recovery = 0.0
    if not website:
        tw0 = time.time()
        try:
            recovered = recover_website(name, category=category)
            if recovered:
                website = recovered
                home_html = fetch_html(page, website, timeout=20000, idle_timeout=2500)
                if home_html:
                    emails, socials, _ = harvest(home_html)
                    _merge(acc, emails, socials)
                    footer_emails = _extract_footer_emails(home_html)
                    _merge(acc, footer_emails, {})
                    note_email_source("Website (recovered)", website)
        except Exception as exc:
            logger.warning("website recovery failed for %s: %s", name, exc)
        t_website_recovery = time.time() - tw0

    # ---- STEP 3: contact / info pages (all paths, concurrent HTTP) ----
    # Email crawl always runs all paths — we don't stop early on email because
    # the first email found may be low-priority (e.g. privacy@) while a better
    # business address sits on /press or /contact. LinkedIn/Telegram still exit
    # early once found. All paths are fetched concurrently so this is fast.
    t2 = time.time()
    batch = {}
    targets = []
    if website:
        root = root_domain_url(website)
        if root:
            targets = [urljoin(root + "/", p.lstrip("/")) for p in CONTACT_PATHS]

            # Also fetch secondary org domains discovered from the homepage
            # (e.g. cardanofoundation.org linked from cardano.org).
            secondary_roots = _secondary_domains(home_html, root, name)
            for sec_root in secondary_roots:
                for path in ["/contact", "/contact-us", "/about", "/team", "/press", "/foundation"]:
                    targets.append(urljoin(sec_root + "/", path.lstrip("/")))

            # Dynamic link discovery: parse homepage for internal contact-like links.
            discovered = _discover_contact_links(home_html, root)
            for link in discovered:
                if link not in targets:
                    targets.append(link)

            batch = _fetch_batch(targets)

            for target in targets:
                page_html = batch.get(target, "")
                if not page_html:
                    continue
                emails, socials, _ = harvest(page_html)
                _merge(acc, emails, socials)
                # Also pull emails specifically from footer elements
                # (catches contacts that are visually in the footer but not
                #  in the raw text near the <a href="mailto:"> link)
                footer_emails = _extract_footer_emails(page_html)
                _merge(acc, footer_emails, {})
                note_email_source("Contact Page", target)
    t_contact = time.time() - t2

    # ---- STEP 3.5: browser fallback for JS-rendered contact pages ----
    # If mandatory fields are still missing and key contact pages returned very
    # thin HTML via static HTTP, re-fetch up to 3 via the browser (Playwright).
    t2b = time.time()
    if _needs_more(acc) and website:
        root = root_domain_url(website)
        if root:
            rendered = 0
            for path in _BROWSER_FALLBACK_PATHS:
                if rendered >= 3 or not _needs_more(acc):
                    break
                target = urljoin(root + "/", path.lstrip("/"))
                static_html = batch.get(target, "")
                # Only use browser if static fetch returned < 500 chars (likely JS-only).
                if len(static_html) < 500:
                    try:
                        browser_html = fetch_html(page, target, timeout=12000, idle_timeout=2000)
                        if browser_html and len(browser_html) > len(static_html):
                            emails, socials, _ = harvest(browser_html)
                            _merge(acc, emails, socials)
                            note_email_source("Contact Page (JS)", target)
                            rendered += 1
                    except Exception as exc:
                        logger.warning("browser fallback failed for %s: %s", target, exc)
    t_browser_fallback = time.time() - t2b

    # ---- STEP 3.6: founder extraction from already-fetched pages ----
    # Runs on ALL fetched pages (home + every contact/about page).
    # Team/people pages are in the batch already; no extra HTTP requests needed.
    founder_pages = []
    if home_html:
        founder_pages.append(home_html)
    for h in batch.values():
        if h and h not in founder_pages:
            founder_pages.append(h)
    founder_name, founder_linkedin = _extract_founders(founder_pages)

    # ---- STEP 4: search recovery for still-missing LinkedIn / Telegram ----
    linkedin_recovery_attempted = not acc["linkedin"]
    linkedin_recovered = False
    t3a = time.time()
    if not acc["linkedin"]:
        try:
            for url in recover_linkedin(name, website, acc["emails"]):
                if url not in acc["linkedin"]:
                    acc["linkedin"].append(url)
            linkedin_recovered = bool(acc["linkedin"])
        except Exception as exc:
            logger.warning("linkedin recovery failed for %s: %s", name, exc)
    t_linkedin_recovery = time.time() - t3a

    telegram_recovery_attempted = not acc["telegram"]
    telegram_recovered = False
    t3b = time.time()
    if not acc["telegram"]:
        try:
            for url in recover_telegram(name, website, acc["emails"]):
                if url not in acc["telegram"]:
                    acc["telegram"].append(url)
            telegram_recovered = bool(acc["telegram"])
        except Exception as exc:
            logger.warning("telegram recovery failed for %s: %s", name, exc)
    t_telegram_recovery = time.time() - t3b

    # ---- STEP 4.5: email search recovery ----
    # Run when: no emails found, OR only low-quality emails found (e.g. off-domain
    # generic addresses) and the project has a known website.
    _prefer = host_of(website)
    _need_email_recovery = bool(website) and not has_quality_email(acc["emails"], _prefer)
    email_recovery_attempted = _need_email_recovery
    email_recovered = False
    t4 = time.time()
    if _need_email_recovery:
        try:
            for email in recover_email(name, website, acc["linkedin"]):
                if email not in acc["emails"]:
                    acc["emails"].append(email)
            if acc["emails"]:
                email_source = "Search Recovery"
                email_recovered = True
        except Exception as exc:
            logger.warning("email recovery failed for %s: %s", name, exc)
    t_email_recovery = time.time() - t4

    # ---- STEP 5: GitHub search recovery ----
    github_recovery_attempted = not acc["github"] and bool(website)
    github_recovered = False
    t5 = time.time()
    if not acc["github"] and website:
        try:
            for url in recover_github(name, website, acc["emails"]):
                if url not in acc["github"]:
                    acc["github"].append(url)
            github_recovered = bool(acc["github"])
        except Exception as exc:
            logger.warning("github recovery failed for %s: %s", name, exc)
    t_github_recovery = time.time() - t5

    # ---- STEP 6: founder LinkedIn search recovery ----
    # Only runs when founder name was extracted but no LinkedIn was found on-page.
    t6 = time.time()
    if founder_name and not founder_linkedin:
        try:
            result = recover_founder_linkedin(founder_name, website, name)
            if result:
                founder_linkedin = result
        except Exception as exc:
            logger.warning("founder LinkedIn recovery failed for %s: %s", name, exc)
    t_founder_li_recovery = time.time() - t6

    # ---- STEP 7: founder web search when no on-site founder found ----
    # If _extract_founders came up empty, search "[project] founder" to get
    # at least a name (and possibly a LinkedIn) from public web results.
    t7 = time.time()
    if not founder_name and website:
        try:
            fn, fli = recover_founder_search(name, website)
            if fn:
                founder_name = fn
                if fli and not founder_linkedin:
                    founder_linkedin = fli
        except Exception as exc:
            logger.warning("founder search failed for %s: %s", name, exc)
    t_founder_search = time.time() - t7

    t_total = time.time() - t_start

    logger.info(
        "Timing %s | platform=%.1fs website=%.1fs web_rec=%.1fs contact=%.1fs browser=%.1fs "
        "li_rec=%.1fs tg_rec=%.1fs email_search=%.1fs total=%.1fs",
        name, t_platform, t_website, t_website_recovery, t_contact, t_browser_fallback,
        t_linkedin_recovery, t_telegram_recovery, t_email_recovery, t_total,
    )

    # ALL useful business emails, priority-sorted, "; " joined.
    prefer = host_of(website)
    email_field = join_business_emails(acc["emails"], prefer_domain=prefer)

    # Description: try platform __NEXT_DATA__ first, then website meta tag,
    # then pre-seeded description from the collector (e.g. DeFiLlama protocols API).
    description = _extract_nextdata_description(html)
    if not description and home_html:
        description = _extract_description(home_html)
    if not description:
        description = (seeds.get("description") or "").strip()

    row = {
        "Company / Project Name": name or "Unknown",
        "Official Website URL":   website or NA,
        "Official Email IDs":     email_field,
        "Contact Page URL":       contact_page_url or NA,
        "LinkedIn URLs":          join_urls(acc["linkedin"]),
        "GitHub URLs":            join_urls(acc["github"]),
        "Twitter/X URLs":         join_urls(acc["twitter"], limit=3),
        "Telegram URLs":          join_urls(acc["telegram"]),
        "Discord URLs":           join_urls(acc["discord"]),
        "Founder Name":           founder_name or NA,
        "Founder LinkedIn":       founder_linkedin or NA,
        "Industry / Category":    category or NA,
        "Short Description":      description or NA,
        "Source Platform":        platform,
        "Discovery URL":          project_url,
    }

    logger.info(
        "Enriched %s | website=%s emails=%s linkedin=%s telegram=%s github=%s founder=%s",
        row["Company / Project Name"],
        row["Official Website URL"],
        row["Official Email IDs"],
        row["LinkedIn URLs"],
        row["Telegram URLs"],
        row["GitHub URLs"],
        founder_name or "—",
    )

    contact_pages_with_content = sum(1 for h in batch.values() if h)

    stage_metrics = {
        "t_platform":             round(t_platform, 3),
        "t_website":              round(t_website, 3),
        "t_website_recovery":     round(t_website_recovery, 3),
        "t_contact":              round(t_contact, 3),
        "t_browser_fallback":     round(t_browser_fallback, 3),
        "t_linkedin_recovery":    round(t_linkedin_recovery, 3),
        "t_telegram_recovery":    round(t_telegram_recovery, 3),
        "t_email_recovery":       round(t_email_recovery, 3),
        "t_github_recovery":      round(t_github_recovery, 3),
        "t_founder_li_recovery":  round(t_founder_li_recovery, 3),
        "t_founder_search":       round(t_founder_search, 3),
        "website_found":          bool(website),
        "email_found":            email_field not in ("", NA),
        "linkedin_found":         bool(acc["linkedin"]),
        "telegram_found":         bool(acc["telegram"]),
        "twitter_found":          bool(acc["twitter"]),
        "discord_found":          bool(acc["discord"]),
        "github_found":           bool(acc["github"]),
        "founder_name_found":     bool(founder_name),
        "founder_linkedin_found": bool(founder_linkedin),
        "contact_pages_attempted":    len(targets),
        "contact_pages_with_content": contact_pages_with_content,
        "linkedin_recovery_attempted":  linkedin_recovery_attempted,
        "telegram_recovery_attempted":  telegram_recovery_attempted,
        "email_recovery_attempted":     email_recovery_attempted,
        "github_recovery_attempted":    github_recovery_attempted,
        "linkedin_recovered":   linkedin_recovered,
        "telegram_recovered":   telegram_recovered,
        "email_recovered":      email_recovered,
        "github_recovered":     github_recovered,
        "recovery_used": (
            linkedin_recovery_attempted
            or telegram_recovery_attempted
            or email_recovery_attempted
            or github_recovery_attempted
        ),
        "recovery_success": bool(
            linkedin_recovered or telegram_recovered
            or email_recovered or github_recovered
        ),
    }

    return row, stage_metrics
