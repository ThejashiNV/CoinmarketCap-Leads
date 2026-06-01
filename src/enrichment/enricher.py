import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.scraping.browser import fetch_html
from src.enrichment.platform_links import extract_platform_links
from src.enrichment.store import missing_fields, NA
from utils.email_tools import extract_emails, choose_best_email, email_confidence
from utils.search_recovery import recover_linkedin, recover_telegram
from utils.social_tools import extract_socials, all_urls
from utils.text_tools import clean_project_name
from utils.url_tools import normalize_url, root_domain_url, join_urls, host_of
from utils.website_validator import is_valid_website


logger = logging.getLogger("scraper")

_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _fetch_static(url, timeout=8):
    """Fast HTTP GET for static pages (no JS rendering). Returns HTML or ""."""
    try:
        resp = requests.get(url, headers=_HTTP_HEADERS, timeout=timeout,
                            allow_redirects=True)
        if resp.status_code == 200 and resp.text:
            return resp.text
    except requests.RequestException:
        pass
    return ""


def _fetch_batch(urls, max_workers=6, timeout=8):
    """Fetch multiple URLs concurrently via plain HTTP. Returns {url: html}.

    Contact/about/team pages are nearly always static HTML — no JS rendering
    needed. Fetching them via requests instead of Playwright saves ~2-3s per
    page AND lets us fire them all concurrently (vs sequential browser navs).
    """
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

CONTACT_PATHS = [
    "/contact",
    "/contact-us",
    "/about",
    "/about-us",
    "/team",
    "/company",
    "/privacy",
    "/privacy-policy",
    "/community",
    "/support",
    "/careers",
    "/jobs",
    "/press",
    "/terms",
]

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


def _needs_more(acc):
    """True while any non-website mandatory field is still empty."""
    return not (acc["emails"] and acc["linkedin"] and acc["telegram"])


def _refine_name(html, fallback_name, website):
    if fallback_name:
        return fallback_name
    soup = BeautifulSoup(html or "", "lxml")
    title = soup.title.get_text(strip=True) if soup.title else ""
    if title:
        # Listing/title pages append marketing copy after a separator.
        name = re.split(r"[|\-–—:]", title)[0].strip()
        name = clean_project_name(name)
        if name:
            return name
    if website:
        host = normalize_url(website).split("//")[-1]
        return host.split(".")[0].capitalize()
    return fallback_name or "Unknown"


def enrich_project(page, project):
    """Run the multi-source fallback pipeline for a single project."""
    project_url = project["Project URL"]
    platform = project.get("Platform", "")
    source_url = project.get("Source URL", "")
    name = clean_project_name(project.get("Project Name", ""))

    acc = _new_accumulator()
    website = ""
    email_source = None

    def note_email_source(stage):
        nonlocal email_source
        if email_source is None and acc["emails"]:
            email_source = stage

    # ---- STEP 1: platform project page (authoritative structured links) ----
    # Emails are intentionally NOT mined here: any address on the aggregator's
    # own page belongs to the aggregator, not the project.
    t0 = time.time()
    html = fetch_html(page, project_url, timeout=25000, idle_timeout=3000)
    website, socials = extract_platform_links(platform, html)
    _merge(acc, [], socials)
    name = _refine_name(html, name, website)
    t_platform = time.time() - t0

    # ---- STEP 2: official website homepage ----
    t1 = time.time()
    home_html = ""
    if website and _needs_more(acc):
        root = root_domain_url(website)
        home_html = fetch_html(page, website, timeout=20000, idle_timeout=2500)
        emails, socials, websites = harvest(home_html)
        _merge(acc, emails, socials)
        note_email_source("Website")
    t_website = time.time() - t1

    # ---- STEP 3: contact/about/team/privacy/company pages ----
    # These are static HTML pages — fetch them all concurrently via plain HTTP
    # instead of sequential browser navigations (~0.3s each vs ~3s sequential).
    t2 = time.time()
    if _needs_more(acc) and website:
        root = root_domain_url(website)
        if root:
            targets = [urljoin(root + "/", p.lstrip("/")) for p in CONTACT_PATHS]

            batch = _fetch_batch(targets)
            for target in targets:
                if not _needs_more(acc):
                    break
                page_html = batch.get(target, "")
                if not page_html:
                    continue
                emails, socials, websites = harvest(page_html)
                _merge(acc, emails, socials)
                note_email_source("Contact Page")
    t_contact = time.time() - t2

    # ---- STEP 4: best-effort search recovery for still-missing socials ----
    t3 = time.time()
    # The mandatory fields LinkedIn and Telegram are often absent from a
    # project's own pages. Recover them from public web search, token-validated
    # so we never attach the wrong company's profile. Best-effort: any failure
    # leaves the field empty rather than breaking the run.
    if not acc["linkedin"]:
        try:
            for url in recover_linkedin(name, website, acc["emails"]):
                if url not in acc["linkedin"]:
                    acc["linkedin"].append(url)
        except Exception as exc:
            logger.warning("linkedin recovery failed for %s: %s", name, exc)

    if not acc["telegram"]:
        try:
            for url in recover_telegram(name, website, acc["emails"]):
                if url not in acc["telegram"]:
                    acc["telegram"].append(url)
        except Exception as exc:
            logger.warning("telegram recovery failed for %s: %s", name, exc)

    t_recovery = time.time() - t3
    t_total = time.time() - t0

    logger.info(
        "Timing %s | platform=%.1fs website=%.1fs contact=%.1fs recovery=%.1fs total=%.1fs",
        name, t_platform, t_website, t_contact, t_recovery, t_total,
    )

    best_email = choose_best_email(acc["emails"], prefer_domain=host_of(website))

    row = {
        "Project Name": name or "Unknown",
        "Platform": platform,
        "Source URL": source_url,
        "Project Page URL": project_url,
        "Official Website URL": website or NA,
        "Official Email ID": best_email or NA,
        "Email Source": email_source or "Not Found",
        "Email Confidence": email_confidence(best_email),
        "LinkedIn URLs": join_urls(acc["linkedin"]),
        "Telegram URLs": join_urls(acc["telegram"]),
        "Twitter URLs": join_urls(acc["twitter"], limit=3),
        "Discord URLs": join_urls(acc["discord"]),
        "Github URLs": join_urls(acc["github"]),
    }

    missing = missing_fields(row)
    row["Missing Fields"] = ", ".join(missing) if missing else "None"

    logger.info(
        "Enriched %s | website=%s email=%s missing=%s",
        row["Project Name"],
        row["Official Website URL"],
        row["Official Email ID"],
        row["Missing Fields"],
    )
    return row
