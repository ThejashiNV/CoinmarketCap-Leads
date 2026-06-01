import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.scraping.browser import fetch_html
from src.enrichment.platform_links import extract_platform_links
from src.enrichment.store import missing_fields, NA
from utils.email_tools import extract_emails, choose_best_email, email_confidence
from utils.search_recovery import recover_linkedin, recover_telegram, recover_email
from utils.social_tools import extract_socials, all_urls
from utils.text_tools import clean_project_name
from utils.url_tools import normalize_url, root_domain_url, join_urls, host_of
from utils.website_validator import is_valid_website


logger = logging.getLogger("scraper")

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
    "/media",
    "/foundation",
    "/ecosystem",
]

SOCIAL_KEYS = ["linkedin", "telegram", "twitter", "discord", "github"]

# Anchor text / hrefs that point at the kind of page where a project tends to
# publish a contact address. Used to follow the site's *real* links so we also
# reach contact/about/team pages that live at non-standard paths the guessed
# CONTACT_PATHS list would miss (e.g. "/pages/contact", "/en/company/about").
_CONTACT_LINK_RE = re.compile(
    r"contact|about|team|career|jobs?|press|media|support|community|"
    r"foundation|ecosystem|partnership|imprint|impressum|legal|privacy",
    re.IGNORECASE,
)
_NON_PAGE_SUFFIXES = (".pdf", ".doc", ".docx", ".zip", ".png", ".jpg", ".jpeg", ".svg")


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


def _discover_contact_links(home_html, root, limit=8):
    """Same-domain links on the homepage that look like contact/about pages.

    Complements the guessed CONTACT_PATHS by following the site's own navigation
    so contact info at non-standard paths is still reached. Stays on the project
    domain and skips documents/assets. Returns absolute, de-duplicated URLs.
    """
    if not home_html or not root:
        return []
    host = host_of(root)
    soup = BeautifulSoup(home_html, "lxml")
    found = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("mailto:", "tel:", "#", "javascript:")):
            continue
        text = a.get_text(" ", strip=True)
        if not (_CONTACT_LINK_RE.search(href) or _CONTACT_LINK_RE.search(text)):
            continue
        full = urljoin(root + "/", href)
        if not full.startswith("http") or host_of(full) != host:
            continue
        norm = full.split("#")[0].split("?")[0].rstrip("/")
        if not norm or norm in seen or norm.lower().endswith(_NON_PAGE_SUFFIXES):
            continue
        seen.add(norm)
        found.append(norm)
        if len(found) >= limit:
            break
    return found


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
    html = fetch_html(page, project_url, timeout=25000, idle_timeout=5000)
    website, socials = extract_platform_links(platform, html)
    _merge(acc, [], socials)
    name = _refine_name(html, name, website)

    # ---- STEP 2: official website homepage ----
    if website and _needs_more(acc):
        root = root_domain_url(website)
        home_html = fetch_html(page, website, timeout=20000, idle_timeout=4000)
        emails, socials, websites = harvest(home_html)
        _merge(acc, emails, socials)
        note_email_source("Website")

        # ---- STEP 3: contact/about/team/privacy/company pages ----
        # Guessed standard paths first, then the homepage's own contact-type
        # links (catches non-standard paths). De-duplicated, same order.
        if _needs_more(acc) and root:
            targets = [urljoin(root + "/", p.lstrip("/")) for p in CONTACT_PATHS]
            for link in _discover_contact_links(home_html, root):
                if link not in targets:
                    targets.append(link)

            for target in targets:
                if not _needs_more(acc):
                    break
                page_html = fetch_html(page, target, timeout=15000, idle_timeout=3000, retries=1)
                if not page_html:
                    continue
                emails, socials, websites = harvest(page_html)
                _merge(acc, emails, socials)
                note_email_source("Contact Page")

    # ---- STEP 4: best-effort search recovery for still-missing socials ----
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

    # ---- STEP 5: best-effort email recovery (only when still missing) ----
    # When the website crawl found no email but a LinkedIn identity exists, use
    # the discovered company identity + website domain as search context. This
    # runs ONLY if acc["emails"] is empty, so website-derived emails always win
    # and a recovered address can never overwrite a higher-confidence one. The
    # recovery itself only accepts addresses on the project's own domain and
    # never constructs/guesses one.
    if not acc["emails"] and acc["linkedin"] and website:
        try:
            recovered = recover_email(name, website, acc["linkedin"])
            for email in recovered:
                if email not in acc["emails"]:
                    acc["emails"].append(email)
            if acc["emails"]:
                note_email_source("Search Recovery")
        except Exception as exc:
            logger.warning("email recovery failed for %s: %s", name, exc)

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
