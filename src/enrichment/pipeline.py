import logging
import os

import pandas as pd

from src.collectors.platforms.listing import collect_projects
from src.enrichment.enricher import enrich_project
from src.enrichment.export import export_leads
from src.enrichment.store import ResultsStore
from src.scraping.browser import browser_page
from utils.platform_detector import detect_platform, SUPPORTED_PLATFORMS


OUTPUT_DIR = "output"
LOG_DIR = "logs"

PROJECTS_CSV = os.path.join(OUTPUT_DIR, "projects.csv")
STORE_PATH = os.path.join(OUTPUT_DIR, "enrich_results.json")
FINAL_CSV = os.path.join(OUTPUT_DIR, "final_leads.csv")
FINAL_XLSX = os.path.join(OUTPUT_DIR, "final_leads.xlsx")

logger = logging.getLogger("scraper")


def _setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    if not logger.handlers:
        handler = logging.FileHandler(os.path.join(LOG_DIR, "extraction.log"), encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)


def run_pipeline(listing_url, emit=print, limit=None):
    """Collect projects from a listing URL and enrich each into a lead row.

    `emit` is a callback for human-readable progress (stdout by default; the
    backend swaps in a log collector for SSE streaming).
    """
    _setup_logging()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    platform = detect_platform(listing_url)
    if not platform:
        raise ValueError(
            f"Unsupported platform URL. Supported: {', '.join(SUPPORTED_PLATFORMS)}"
        )

    emit(f"Platform detected: {platform}")
    emit(f"Collecting projects from: {listing_url}")

    projects = collect_projects(listing_url)
    emit(f"Collected {len(projects)} projects.")

    if limit:
        projects = projects[:limit]
        emit(f"Limiting this run to {len(projects)} projects.")

    if projects:
        pd.DataFrame(projects).to_csv(PROJECTS_CSV, index=False)

    store = ResultsStore(STORE_PATH)
    total = len(projects)

    with browser_page() as page:
        for index, project in enumerate(projects, start=1):
            url = project["Project URL"]
            name = project.get("Project Name") or url

            if not store.should_process(url):
                emit(f"[{index}/{total}] Skip (already complete): {name}")
                continue

            emit(f"[{index}/{total}] Enriching: {name}")
            try:
                row = enrich_project(page, project)
                store.record(url, row)
                emit(
                    f"    website={row['Official Website URL']} | "
                    f"email={row['Official Email ID']} | "
                    f"missing={row['Missing Fields']}"
                )
            except Exception as exc:
                logger.exception("Failed enriching %s: %s", name, exc)
                emit(f"    error: {exc}")

    rows = store.rows_for([p["Project URL"] for p in projects])
    df = export_leads(rows, FINAL_CSV, FINAL_XLSX)

    emit(f"Exported {len(df)} leads to {FINAL_CSV} and {FINAL_XLSX}")
    logger.info("Pipeline complete: %s leads from %s", len(df), listing_url)
    return df
