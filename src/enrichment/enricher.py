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
)
from utils.search_recovery import recover_linkedin, recover_telegram, recover_email
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
    "/contact",
    "/contact-us",
    "/about",
    "/about-us",
    "/team",
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
    r"partners?|foundation|careers?|jobs?|impressum|imprint)\b",
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
        note_email_source("Website", website)
    t_website = time.time() - t1

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
    email_recovery_attempted = not acc["emails"] and bool(website)
    email_recovered = False
    t4 = time.time()
    if not acc["emails"] and website:
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

    t_total = time.time() - t0

    logger.info(
        "Timing %s | platform=%.1fs website=%.1fs contact=%.1fs browser=%.1fs "
        "li_rec=%.1fs tg_rec=%.1fs email_search=%.1fs total=%.1fs",
        name, t_platform, t_website, t_contact, t_browser_fallback,
        t_linkedin_recovery, t_telegram_recovery, t_email_recovery, t_total,
    )

    # ALL useful business emails, priority-sorted, "; " joined.
    prefer = host_of(website)
    email_field = join_business_emails(acc["emails"], prefer_domain=prefer)

    # Description: try platform __NEXT_DATA__ first, then website meta tag.
    description = _extract_nextdata_description(html)
    if not description and home_html:
        description = _extract_description(home_html)

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
        "Founder Name":           NA,
        "Founder LinkedIn":       NA,
        "Industry / Category":    category or NA,
        "Short Description":      description or NA,
        "Source Platform":        platform,
        "Discovery URL":          project_url,
    }

    logger.info(
        "Enriched %s | website=%s emails=%s linkedin=%s telegram=%s",
        row["Company / Project Name"],
        row["Official Website URL"],
        row["Official Email IDs"],
        row["LinkedIn URLs"],
        row["Telegram URLs"],
    )

    contact_pages_with_content = sum(1 for h in batch.values() if h)

    stage_metrics = {
        "t_platform":          round(t_platform, 3),
        "t_website":           round(t_website, 3),
        "t_contact":           round(t_contact, 3),
        "t_browser_fallback":  round(t_browser_fallback, 3),
        "t_linkedin_recovery": round(t_linkedin_recovery, 3),
        "t_telegram_recovery": round(t_telegram_recovery, 3),
        "t_email_recovery":    round(t_email_recovery, 3),
        "website_found":       bool(website),
        "email_found":         email_field not in ("", NA),
        "linkedin_found":      bool(acc["linkedin"]),
        "telegram_found":      bool(acc["telegram"]),
        "twitter_found":       bool(acc["twitter"]),
        "discord_found":       bool(acc["discord"]),
        "contact_pages_attempted":    len(targets),
        "contact_pages_with_content": contact_pages_with_content,
        "linkedin_recovery_attempted": linkedin_recovery_attempted,
        "telegram_recovery_attempted": telegram_recovery_attempted,
        "email_recovery_attempted":    email_recovery_attempted,
        "linkedin_recovered":  linkedin_recovered,
        "telegram_recovered":  telegram_recovered,
        "email_recovered":     email_recovered,
        "recovery_used": (
            linkedin_recovery_attempted
            or telegram_recovery_attempted
            or email_recovery_attempted
        ),
        "recovery_success": bool(linkedin_recovered or telegram_recovered or email_recovered),
    }

    return row, stage_metrics
