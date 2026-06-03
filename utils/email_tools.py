import re
from html import unescape


EMAIL_REGEX = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# A well-formed domain: dot-separated labels, alphabetic TLD >= 2 chars.
DOMAIN_REGEX = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?)*"
    r"\.[A-Za-z]{2,}$"
)

# Aggregator/listing domains — their support emails are not project leads.
REJECT_EMAIL_DOMAINS = (
    "coinmarketcap.com",
    "coingecko.com",
    "coinranking.com",
    "sentry.io",
    "cloudflare.com",
    "wixpress.com",
    "godaddy.com",
    "gstatic.com",
    "googleapis.com",
    "google-analytics.com",
    "jsdelivr.net",
    "cloudfront.net",
    # Site builders / hosting platforms — never the project's own address.
    "lovable.dev",
    "vercel.app",
    "netlify.app",
    "netlify.com",
    "github.io",
    "pages.dev",
    "web.app",
    "firebaseapp.com",
    "wordpress.com",
    "wixsite.com",
    "squarespace.com",
    "webflow.io",
    # Job boards / HR platforms that appear on careers/jobs pages.
    "lever.co",
    "greenhouse.io",
    "bamboohr.com",
    "workable.com",
    "ashbyhq.com",
    "zodl.com",
    "breezy.hr",
    "recruitee.com",
    "smartrecruiters.com",
    # News / media sites whose emails leak from ads, widgets, or press pages.
    "express.co.uk",
    "reachplc.com",
    "mirror.co.uk",
    "dailymail.co.uk",
    "thesun.co.uk",
    "bbc.co.uk",
    "bbc.com",
    "cnn.com",
    "nytimes.com",
    "theguardian.com",
    "forbes.com",
    "bloomberg.com",
    # Crypto news sites — never a project's own contact address.
    "coindesk.com",
    "cointelegraph.com",
    "decrypt.co",
    "theblock.co",
    "defiant.io",
    "bitcoinmagazine.com",
    "beincrypto.com",
    "cryptoslate.com",
    "newsbtc.com",
    "coinspeaker.com",
    "ambcrypto.com",
    "u.today",
    "cryptopotato.com",
    "cryptobriefing.com",
    # Analytics / data platforms whose emails appear on partner pages.
    "chainalysis.com",
    "nansen.ai",
    "dune.com",
    "glassnode.com",
    "messari.io",
    "certik.com",
    # Audit firms — their emails leak from security pages.
    "hacken.io",
    "trailofbits.com",
    "openzeppelin.com",
    "quantstamp.com",
    "peckshield.com",
    "slowmist.com",
    "immunefi.com",
    # Design / dev tool domains that leak from embedded widgets.
    "figma.com",
    "notion.so",
    "typeform.com",
    "webflow.com",
    # UK/EU press regulator and media company domains.
    "ipso.co.uk",
    "pressgazette.co.uk",
    "ofcom.org.uk",
    "goskippy.com",
    "moneysupermarket.com",
    # Crypto lending / DeFi aggregator emails that leak from partner pages.
    "coinrabbit.io",
    "nexo.io",
    "celsius.network",
    "blockfi.com",
)

# Hard-excluded local-parts. These are NEVER returned regardless of domain or
# score. Includes automated mailboxes and addresses the user explicitly said to
# exclude (privacy@, legal@, security@, etc.).
JUNK_LOCALPARTS = (
    "noreply",
    "no-reply",
    "do-not-reply",
    "donotreply",
    "abuse",
    "postmaster",
    "mailer-daemon",
    "mailerdaemon",
    "dmca",
    "bounce",
    "bounces",
    "automated",
    "automation",
    "notifications",
    "notification",
    "alerts",
    "alert",
    # Explicitly excluded by spec — useful for compliance but not outreach
    "privacy",
    "privacy-policy",
    "legal",
    "security",
    "unsubscribe",
    "optout",
    "spam",
    # Infrastructure mailboxes — never respond to business outreach.
    "webmaster",
    "hostmaster",
    "root",
    "sysadmin",
    "administrator",
)

# Cloudflare email protection: <span class="__cf_email__" data-cfemail="hex">
# and <a href="/cdn-cgi/l/email-protection#hex">
CF_ATTR_REGEX = re.compile(r'data-cfemail="([0-9a-fA-F]+)"')
CF_HREF_REGEX = re.compile(r'/cdn-cgi/l/email-protection#([0-9a-fA-F]+)')

MAILTO_REGEX = re.compile(r'mailto:([^"\'?>\s]+)', re.IGNORECASE)

# " name (at) domain (dot) com " style obfuscation.
OBFUSCATION_PATTERNS = [
    (re.compile(r"\s*[\(\[\{]\s*at\s*[\)\]\}]\s*", re.IGNORECASE), "@"),
    (re.compile(r"\s+at\s+", re.IGNORECASE), "@"),
    (re.compile(r"\s*[\(\[\{]\s*dot\s*[\)\]\}]\s*", re.IGNORECASE), "."),
    (re.compile(r"\s+dot\s+", re.IGNORECASE), "."),
]

JUNK_SUBSTRINGS = [
    "example",
    "test@",
    "@test",
    "noreply",
    "no-reply",
    "donotreply",
    "@sentry",
    "sentry.io",
    "wixpress",
    "@cloudflare",
    "cloudflare.com",
    "godaddy",
    "@2x",
    "@3x",
    "yourdomain",
    "domain.com",
    "email.com",
    "sentry-next",
    "u003e",
    # Template / placeholder emails that appear in docs or example code.
    "you@company",
    "you@your",
    "your@email",
    "your@company",
    "name@company",
    "name@domain",
    "user@domain",
    "info@example",
    "contact@example",
    "yourname@",
    "yourcompany",
    "youremail",
    "changeme",
    "placeholder",
    "someone@somewhere",
]

ASSET_SUFFIXES = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
    ".js",
    ".css",
    ".json",
    ".xml",
    ".woff",
    ".woff2",
)

PERSONAL_DOMAINS = (
    "gmail.com",
    "yahoo.com",
    "hotmail.com",
    "outlook.com",
    "icloud.com",
    "proton.me",
    "protonmail.com",
    "aol.com",
    "gmx.com",
    "mail.com",
)

# Business email keywords ranked by outreach value (index 0 = highest).
# Scores are (len - index) * 10 so top keywords dominate.
PREFERRED_KEYWORDS = [
    # Tier 1 — direct business/partnership contact (highest value)
    "partnerships",
    "partnership",
    "business",
    "bd",
    "bizdev",
    "corporate",
    "enterprise",
    "sales",
    # Tier 2 — general contact (high value)
    "contact",
    "hello",
    "hi",
    "info",
    "team",
    # Tier 3 — PR / media (medium-high)
    "press",
    "media",
    "pr",
    # Tier 4 — community / growth (medium)
    "foundation",
    "community",
    "marketing",
    "growth",
    # Tier 5 — general enquiry (lower)
    "general",
    "enquiries",
    "inquiries",
    # Tier 6 — support (acceptable, not ideal)
    "support",
    "help",
]

# These score heavily negative but do NOT hard-filter (still stored if nothing
# better exists). The hard filter is JUNK_LOCALPARTS above.
SOFT_AVOID_KEYWORDS = [
    "admin",
    "webmaster",
    "recruiting",
    "careers",
    "jobs",
    "invest",
    "investor",
]


def decode_cfemail(hex_str):
    """Decode a Cloudflare-obfuscated email hex string."""
    try:
        key = int(hex_str[:2], 16)
        decoded = "".join(
            chr(int(hex_str[i : i + 2], 16) ^ key)
            for i in range(2, len(hex_str), 2)
        )
        return decoded
    except (ValueError, IndexError):
        return ""


def _valid_syntax(email):
    if email.count("@") != 1:
        return False
    local, domain = email.split("@", 1)
    if not local or not domain:
        return False
    if ".." in domain or domain.startswith(".") or domain.endswith("."):
        return False
    return bool(DOMAIN_REGEX.match(domain))


def _is_clean_email(email):
    email_lower = email.lower()
    if not _valid_syntax(email_lower):
        return False
    if email_lower.endswith(ASSET_SUFFIXES):
        return False
    if any(junk in email_lower for junk in JUNK_SUBSTRINGS):
        return False
    local, domain = email_lower.split("@", 1)
    if domain.endswith(REJECT_EMAIL_DOMAINS):
        return False
    # Hard-filter: any local-part that starts with a junk prefix.
    if any(local.startswith(j) or local == j for j in JUNK_LOCALPARTS):
        return False
    # Reject obvious version/asset hashes mistaken as emails.
    if re.search(r"@\d+x", email_lower):
        return False
    return True


def extract_emails(html):
    """Extract every plausible email from raw HTML using all supported methods.

    Returns a de-duplicated, lowercased list (order preserved).
    """
    if not html:
        return []

    text = unescape(html)
    found = []

    # 1. Cloudflare-protected emails.
    for hex_str in CF_ATTR_REGEX.findall(text) + CF_HREF_REGEX.findall(text):
        decoded = decode_cfemail(hex_str)
        if decoded:
            found.append(decoded)

    # 2. mailto: links.
    for raw in MAILTO_REGEX.findall(text):
        found.append(unescape(raw).strip())

    # 3. De-obfuscate "(at)"/"(dot)" then regex the whole document.
    deobfuscated = text
    for pattern, replacement in OBFUSCATION_PATTERNS:
        deobfuscated = pattern.sub(replacement, deobfuscated)

    found.extend(EMAIL_REGEX.findall(text))
    found.extend(EMAIL_REGEX.findall(deobfuscated))

    cleaned = []
    seen = set()
    for email in found:
        email = email.strip().strip(".").lower()
        if "@" not in email:
            continue
        if not EMAIL_REGEX.fullmatch(email):
            continue
        if not _is_clean_email(email):
            continue
        if email not in seen:
            seen.add(email)
            cleaned.append(email)

    return cleaned


def _score(email, prefer_domain=None):
    local = email.split("@", 1)[0].lower()
    domain = email.split("@", 1)[1].lower()

    score = 0
    for i, kw in enumerate(PREFERRED_KEYWORDS):
        if local == kw or local.startswith(kw):
            score += (len(PREFERRED_KEYWORDS) - i) * 10
            break

    if any(kw in local for kw in SOFT_AVOID_KEYWORDS):
        score -= 40

    # Personal webmail domains are very low value.
    if domain.endswith(PERSONAL_DOMAINS):
        score -= 50

    # Strongly prefer an email on the project's own domain.
    if prefer_domain:
        pref = prefer_domain.lower()
        if domain == pref or domain.endswith("." + pref):
            score += 200
        else:
            score -= 30

    return score


def choose_best_email(emails, prefer_domain=None):
    """Pick the single most business-appropriate email (legacy, used by store)."""
    candidates = [e for e in (emails or []) if e]
    if not candidates:
        return ""
    return max(candidates, key=lambda e: _score(e, prefer_domain))


def choose_business_emails(emails, prefer_domain=None):
    """Return ALL useful business emails, priority-sorted, deduped.

    Unlike choose_best_email, this preserves every email that scores above a
    minimum threshold so callers can store the full set (e.g.
    "contact@x.io; partnerships@x.io; press@x.io").

    When a project-domain email is present, off-domain emails are excluded
    unless they clearly belong to an official sister organization (very high
    base score). This prevents partner/campaign platform emails from leaking
    into the output alongside the real contact address.
    """
    candidates = [e for e in (emails or []) if e]
    if not candidates:
        return []

    scored = [(e, _score(e, prefer_domain)) for e in candidates]
    scored.sort(key=lambda t: t[1], reverse=True)

    # Separate on-domain from off-domain results.
    pref = (prefer_domain or "").lower()
    on_domain = [(e, s) for e, s in scored if pref and e.split("@", 1)[1].lower() in (pref, f"mail.{pref}")]
    off_domain = [(e, s) for e, s in scored if (e, s) not in on_domain]

    result = []

    # Always include all positively-scored on-domain emails.
    result.extend(e for e, s in on_domain if s > 0)

    if result:
        # On-domain emails found: only add off-domain if they score very high
        # (suggesting a well-known official address, not a partner platform).
        result.extend(e for e, s in off_domain if s > 200)
    else:
        # No on-domain email at all: include any positively-scored off-domain.
        result.extend(e for e, s in off_domain if s > 0)

    if not result:
        # Last resort: return the absolute best even if negative.
        result = [scored[0][0]] if scored else []

    return result


def join_business_emails(emails, prefer_domain=None):
    """Return a '; '-joined string of all useful business emails, or 'N/A'."""
    chosen = choose_business_emails(emails, prefer_domain)
    return "; ".join(chosen) if chosen else "N/A"


def email_confidence(email_field):
    """Confidence level for the email field (may contain multiple emails)."""
    if not email_field or email_field == "N/A":
        return "LOW"
    # Take the first email (highest-priority) for scoring.
    first = email_field.split(";")[0].strip()
    local = first.split("@", 1)[0].lower() if "@" in first else ""
    high = ("contact", "hello", "info", "team", "partnership", "partnerships",
            "business", "sales", "bd", "bizdev", "press", "media")
    if any(kw in local for kw in high):
        return "HIGH"
    if any(kw in local for kw in ("support", "help", "foundation", "community",
                                   "marketing", "growth")):
        return "MEDIUM"
    return "LOW"
