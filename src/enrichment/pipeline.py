import logging
import os
import time

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


def _get_ram_mb():
    """Current process RSS in MB, or -1 if unavailable."""
    try:
        import psutil
        return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
    except Exception:
        pass
    # Fallback for Linux /proc (works without psutil)
    try:
        with open(f"/proc/{os.getpid()}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024  # kB -> MB
    except Exception:
        pass
    return -1


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

    t_collect_start = time.time()
    projects = collect_projects(listing_url)
    t_collect = time.time() - t_collect_start
    emit(f"Collected {len(projects)} projects.")

    if limit:
        projects = projects[:limit]
        emit(f"Limiting this run to {len(projects)} projects.")

    if projects:
        pd.DataFrame(projects).to_csv(PROJECTS_CSV, index=False)

    store = ResultsStore(STORE_PATH)
    total = len(projects)
    enriched_count = 0
    skipped_count = 0
    failed_count = 0
    project_times = []
    peak_ram = _get_ram_mb()

    t_enrich_start = time.time()

    with browser_page() as page:
        ram_after_launch = _get_ram_mb()
        logger.info("Browser launched | RAM=%.0fMB", ram_after_launch)

        for index, project in enumerate(projects, start=1):
            url = project["Project URL"]
            name = project.get("Project Name") or url

            if not store.should_process(url):
                emit(f"[{index}/{total}] Skip (already complete): {name}")
                skipped_count += 1
                continue

            emit(f"[{index}/{total}] Enriching: {name}")
            t_proj = time.time()
            try:
                row = enrich_project(page, project)
                store.record(url, row)
                enriched_count += 1
                emit(
                    f"    website={row['Official Website URL']} | "
                    f"email={row['Official Email ID']} | "
                    f"missing={row['Missing Fields']}"
                )
            except Exception as exc:
                logger.exception("Failed enriching %s: %s", name, exc)
                emit(f"    error: {exc}")
                failed_count += 1

            dt = time.time() - t_proj
            project_times.append(dt)

            # Track peak RAM
            ram_now = _get_ram_mb()
            if ram_now > peak_ram:
                peak_ram = ram_now

            # Log per-project resource snapshot every 5 projects
            if index % 5 == 0 or index == total:
                logger.info(
                    "Progress %d/%d | RAM=%.0fMB | peak=%.0fMB | last=%.1fs",
                    index, total, ram_now, peak_ram, dt,
                )

    t_enrich_total = time.time() - t_enrich_start

    rows = store.rows_for([p["Project URL"] for p in projects])
    df = export_leads(rows, FINAL_CSV, FINAL_XLSX)

    emit(f"Exported {len(df)} leads to {FINAL_CSV} and {FINAL_XLSX}")

    # ---- Benchmark summary ----
    avg_time = sum(project_times) / len(project_times) if project_times else 0
    total_runtime = t_collect + t_enrich_total
    summary = (
        f"--- Benchmark ---\n"
        f"  Projects: {total} total, {enriched_count} enriched, "
        f"{skipped_count} skipped, {failed_count} failed\n"
        f"  Collection: {t_collect:.1f}s\n"
        f"  Enrichment: {t_enrich_total:.1f}s "
        f"(avg {avg_time:.1f}s/project)\n"
        f"  Total: {total_runtime:.1f}s\n"
        f"  Peak RAM: {peak_ram:.0f}MB\n"
        f"  Browser launches: 1"
    )
    emit(summary)
    logger.info(
        "Benchmark | projects=%d enriched=%d skipped=%d failed=%d "
        "collection=%.1fs enrichment=%.1fs avg=%.1fs/proj total=%.1fs peak_ram=%.0fMB",
        total, enriched_count, skipped_count, failed_count,
        t_collect, t_enrich_total, avg_time, total_runtime, peak_ram,
    )
    return df
