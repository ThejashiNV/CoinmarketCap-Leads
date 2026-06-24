import logging
from contextlib import contextmanager

from playwright.sync_api import sync_playwright


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

logger = logging.getLogger("scraper")

# Container/runtime launch flags. These let Chromium survive inside a Docker
# instance: `--disable-dev-shm-usage` moves shared memory from /dev/shm
# (default 64 MB) to /tmp; `--no-sandbox` is required when running as root.
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
    """Yield a configured Playwright page; guarantees full cleanup on exit.

    Closes context then browser explicitly so Chromium never leaks. A single
    browser + context + page is reused across all projects in a run.
    """
    pw = sync_playwright().start()
    browser = None
    context = None
    try:
        # Use system Chrome when the Playwright Chromium bundle is not installed.
        _SYSTEM_CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        import os as _os
        launch_opts = dict(headless=headless, args=_LAUNCH_ARGS)
        if _os.path.exists(_SYSTEM_CHROME):
            launch_opts["executable_path"] = _SYSTEM_CHROME
        browser = pw.chromium.launch(**launch_opts)
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 720},
            locale="en-US",
        )
        page = context.new_page()
        yield page
    finally:
        # Explicit cleanup chain: page belongs to context, context to browser.
        # Close each layer so no Chromium process survives.
        if context:
            try:
                context.close()
            except Exception:
                pass
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        try:
            pw.stop()
        except Exception:
            pass


def fetch_html(page, url, timeout=20000, idle_timeout=3000, retries=2):
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

            # Release the page's DOM/JS heap before the next navigation.
            try:
                page.goto("about:blank", wait_until="commit", timeout=3000)
            except Exception:
                pass

            return html
        except Exception as exc:
            logger.warning("fetch failed (%s/%s) for %s: %s", attempt, retries, url, exc)

    return ""
