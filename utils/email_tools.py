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
)

# Local-parts that are never useful as outreach leads.
JUNK_LOCALPARTS = (
    "noreply",
    "no-reply",
    "donotreply",
    "abuse",
    "postmaster",
    "mailer-daemon",
    "mailerdaemon",
    "dmca",
    "bounce",
)

# Cloudflare email protection: <span class="__cf_email__" data-cfemail="hex">
# and <a href="/cdn-cgi/l/email-protection#hex">
CF_ATTR_REGEX = re.compile(r'data-cfemail="([0-9a-fA-F]+)"')
CF_HREF_REGEX = re.compile(r'/cdn-cgi/l/email-protection#([0-9a-fA-F]+)')

MAILTO_REGEX = re.compile(r'mailto:([^"\'?>\s]+)', re.IGNORECASE)

# " name (at) domain (dot) com " style obfuscation. Tokens must be bracketed or
# whitespace-delimited so we never rewrite "at"/"dot" hiding inside words
# (e.g. "gstatic" must not become "gst@ic").
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

# Local-part keywords ranked best -> worst.
PREFERRED_KEYWORDS = [
    "business",
    "partnership",
    "partnerships",
    "bd",
    "contact",
    "hello",
    "hi",
    "info",
    "sales",
    "marketing",
    "media",
    "press",
    "team",
    "general",
    "enquiries",
    "inquiries",
]

AVOID_KEYWORDS = [
    "noreply",
    "no-reply",
    "donotreply",
    "notification",
    "notifications",
    "privacy",
    "legal",
    "abuse",
    "security",
    "dmca",
    "webmaster",
    "postmaster",
    "admin",
]


def decode_cfemail(hex_str):
    """Decode a Cloudflare-obfuscated email hex string.

    The first byte is an XOR key; each subsequent byte is XORed with it.
    """
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
    email = email.lower()
    if not _valid_syntax(email):
        return False
    if email.endswith(ASSET_SUFFIXES):
        return False
    if any(junk in email for junk in JUNK_SUBSTRINGS):
        return False
    local, domain = email.split("@", 1)
    if domain.endswith(REJECT_EMAIL_DOMAINS):
        return False
    if local.startswith(JUNK_LOCALPARTS):
        return False
    # Reject obvious version/asset hashes mistaken as emails.
    if re.search(r"@\d+x", email):
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
        if kw in local:
            score += (len(PREFERRED_KEYWORDS) - i) * 10
            break

    if any(kw in local for kw in AVOID_KEYWORDS):
        score -= 100

    # Support is acceptable but not preferred.
    if local in ("support", "help") or local.startswith(("support", "help")):
        score += 1

    # Business domains beat free webmail.
    if domain.endswith(PERSONAL_DOMAINS):
        score -= 20

    # Strongly prefer an email on the project's own domain.
    if prefer_domain:
        pref = prefer_domain.lower()
        if domain == pref or domain.endswith("." + pref):
            score += 200
        else:
            score -= 30

    return score


def choose_best_email(emails, prefer_domain=None):
    """Pick the most business-appropriate email, preferring the site domain."""
    candidates = [e for e in (emails or []) if e]
    if not candidates:
        return ""
    return max(candidates, key=lambda e: _score(e, prefer_domain))


def email_confidence(email):
    if not email:
        return "LOW"
    local = email.split("@", 1)[0].lower()
    high = ("contact", "hello", "info", "team", "partnership", "business", "sales")
    if any(kw in local for kw in high):
        return "HIGH"
    if any(kw in local for kw in ("support", "help", "media", "press")):
        return "MEDIUM"
    return "LOW"
