from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "ref",
    "referrer",
    "source",
    "sharecode",
    "sharesource",
    "fbclid",
    "gclid",
    "igshid",
    "spm",
}


def normalize_url(url):
    """Canonicalize a URL for storage and de-duplication.

    Adds scheme to protocol-relative URLs, lowercases the host, drops www,
    strips fragments and known tracking params, and removes trailing slashes.
    Returns "" for anything that is not an http(s) URL.
    """
    if not url:
        return ""

    url = str(url).strip()

    if url.startswith("//"):
        url = "https:" + url

    if not url.lower().startswith(("http://", "https://")):
        return ""

    try:
        parsed = urlparse(url)
    except Exception:
        return ""

    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]

    if not netloc:
        return ""

    path = parsed.path.rstrip("/")

    kept = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=False)
        if k.lower() not in TRACKING_PARAMS
    ]
    query = urlencode(kept)

    return urlunparse(("https", netloc, path, "", query, ""))


def root_domain_url(url):
    """Return scheme://host for a URL (no path/query), or "" if invalid."""
    normalized = normalize_url(url)
    if not normalized:
        return ""
    parsed = urlparse(normalized)
    return f"https://{parsed.netloc}"


def host_of(url):
    normalized = normalize_url(url)
    if not normalized:
        return ""
    return urlparse(normalized).netloc


def dedupe_urls(urls):
    """De-duplicate a list of URLs by their normalized form, preserving order."""
    seen = set()
    result = []
    for url in urls or []:
        norm = normalize_url(url)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        result.append(norm)
    return result


def join_urls(urls, limit=None):
    """Render a list of URLs as a stable, de-duplicated, sorted string for CSV."""
    deduped = sorted(dedupe_urls(urls))
    if limit is not None:
        deduped = deduped[:limit]
    return "; ".join(deduped) if deduped else "N/A"
