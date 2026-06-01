import logging
from contextlib import contextmanager

from playwright.sync_api import sync_playwright


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

logger = logging.getLogger("scraper")


# Container/runtime launch flags (NOT scraping behaviour). These let Chromium
# survive inside a small Docker instance (e.g. Render): the default 64 MB
# /dev/shm is too small for Chromium and causes tab crashes that look like the
# whole service dying mid-run — `--disable-dev-shm-usage` moves that to /tmp.
# `--no-sandbox` is required when the container runs as root, and the rest trim
# memory/GPU usage that a headless scrape never needs.
_LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-extensions",
    "--disable-background-networking",
    "--no-first-run",
]


@contextmanager
def browser_page(headless=True):
    """Yield a configured Playwright page; guarantees the browser is closed."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, args=_LAUNCH_ARGS)
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1366, "height": 900},
            locale="en-US",
        )
        page = context.new_page()
        try:
            yield page
        finally:
            try:
                browser.close()
            except Exception:
                pass


def fetch_html(page, url, timeout=20000, idle_timeout=4000, retries=2):
    """Navigate to a URL and return its rendered HTML + visible text.

    Appends body inner_text so emails/links that are rendered as text (not in
    anchors) are still captured. Returns "" on failure after retries.
    """
    for attempt in range(1, retries + 1):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            try:
                page.wait_for_load_state("networkidle", timeout=idle_timeout)
            except Exception:
                pass

            html = page.content()
            try:
                html += "\n" + page.inner_text("body")
            except Exception:
                pass
            return html
        except Exception as exc:
            logger.warning("fetch failed (%s/%s) for %s: %s", attempt, retries, url, exc)

    return ""
