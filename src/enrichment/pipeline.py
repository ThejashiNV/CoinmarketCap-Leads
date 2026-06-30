import json
import logging
import os
import queue
import threading
import time
import uuid

import pandas as pd

from src.collectors.platforms.listing import collect_projects
from src.enrichment.enricher import enrich_project
from src.enrichment.export import export_leads
from src.enrichment.store import ResultsStore
from src.telemetry.collector import MetricsCollector
from utils.platform_detector import detect_platform, SUPPORTED_PLATFORMS


OUTPUT_DIR = "output"
LOG_DIR = "logs"

PROJECTS_CSV = os.path.join(OUTPUT_DIR, "projects.csv")
STORE_PATH = os.path.join(OUTPUT_DIR, "enrich_results.json")
FINAL_CSV = os.path.join(OUTPUT_DIR, "final_leads.csv")
FINAL_XLSX = os.path.join(OUTPUT_DIR, "final_leads.xlsx")

logger = logging.getLogger("scraper")

# Each worker maintains its own Chromium process (~200-300 MB RAM each).
# 3 workers is a safe default for servers with ≥1 GB RAM.
DEFAULT_WORKERS = 3


def _setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    if not logger.handlers:
        handler = logging.FileHandler(
            os.path.join(LOG_DIR, "extraction.log"), encoding="utf-8"
        )
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
    try:
        with open(f"/proc/{os.getpid()}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except Exception:
        pass
    return -1


# Memory budget for the memory-aware worker cap.  Each enrichment worker runs
# its own Chromium (peaks ~350 MB under load) on top of a base Python/FastAPI/
# pandas footprint (~300 MB).  These are deliberately conservative so a small
# instance silently uses fewer workers instead of getting OOM-killed mid-run.
_BASE_FOOTPRINT_MB = 300
_PER_WORKER_MB = 350


def _memory_limit_mb():
    """Best-effort memory ceiling for this process, in MB (or None if unknown).

    Prefers the cgroup limit — what a container is actually capped at — because
    ``psutil.virtual_memory().total`` reports *host* RAM inside most container
    runtimes, which would defeat the cap on a memory-limited instance. Falls
    back to psutil host total when no cgroup limit is set.
    """
    candidates = []
    # cgroup v2
    try:
        with open("/sys/fs/cgroup/memory.max") as f:
            val = f.read().strip()
        if val and val != "max":
            candidates.append(int(val))
    except Exception:
        pass
    # cgroup v1
    try:
        with open("/sys/fs/cgroup/memory/memory.limit_in_bytes") as f:
            val = int(f.read().strip())
        # v1 reports a huge sentinel value when unlimited.
        if 0 < val < (1 << 62):
            candidates.append(val)
    except Exception:
        pass
    # Host total (also acts as a ceiling on any over-large cgroup value).
    try:
        import psutil
        candidates.append(psutil.virtual_memory().total)
    except Exception:
        pass
    if not candidates:
        return None
    return min(candidates) / (1024 * 1024)


def _memory_safe_workers(requested):
    """Cap ``requested`` workers so concurrent Chromium instances fit in RAM.

    Returns a value in ``[1, requested]``. When the memory ceiling can't be
    determined, the request is honoured unchanged. Also returns the detected
    limit (MB) for logging — ``(workers, limit_mb)``.
    """
    limit_mb = _memory_limit_mb()
    if not limit_mb:
        return requested, None
    safe = int((limit_mb - _BASE_FOOTPRINT_MB) // _PER_WORKER_MB)
    return max(1, min(requested, safe)), limit_mb


class _Progress:
    """Thread-safe progress tracker shared across all worker threads."""

    def __init__(self, total, workers):
        self._lock = threading.Lock()
        self.total = total
        self.workers = workers
        self.done = 0
        self.failed = 0
        self._times = []           # per-project wall-clock seconds
        self.t_start = time.time()

    def mark_done(self, elapsed_s, failed=False):
        with self._lock:
            self.done += 1
            if failed:
                self.failed += 1
            elif elapsed_s > 0:
                self._times.append(elapsed_s)
            return self.done

    def pct(self):
        with self._lock:
            return round((self.done / self.total) * 100, 1) if self.total else 100

    def eta_seconds(self):
        with self._lock:
            remaining = self.total - self.done
            if not self._times or remaining <= 0:
                return 0
            avg = sum(self._times) / len(self._times)
            # Wall-clock ETA: remaining work spread across all workers.
            return max(0, (remaining * avg) / self.workers)

    def avg_time(self):
        with self._lock:
            return sum(self._times) / len(self._times) if self._times else 0


def _progress_msg(prog, project_name):
    """Emit a structured JSON progress line parseable by the backend/frontend."""
    return json.dumps({
        "type": "progress",
        "done": prog.done,
        "total": prog.total,
        "pct": prog.pct(),
        "project": project_name,
        "eta": int(prog.eta_seconds()),
        "workers": prog.workers,
    })


def _worker(project_queue, results, prog, store, emit, collector, worker_id):
    """
    Worker thread: creates its own Playwright instance + Chromium browser,
    pulls projects from the shared queue, and enriches each one.

    Each thread owns its playwright/browser objects exclusively — Playwright's
    sync_api is not thread-safe to share across threads, but separate instances
    in separate threads are fully supported.
    """
    import os as _os
    from playwright.sync_api import sync_playwright
    from src.scraping.browser import _LAUNCH_ARGS, USER_AGENT

    pw = sync_playwright().start()
    browser = None
    ctx = None
    try:
        _SYSTEM_CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        _launch_opts = dict(headless=True, args=_LAUNCH_ARGS)
        if _os.path.exists(_SYSTEM_CHROME):
            _launch_opts["executable_path"] = _SYSTEM_CHROME
        browser = pw.chromium.launch(**_launch_opts)
        ctx = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 720},
            locale="en-US",
        )
        page = ctx.new_page()

        while True:
            try:
                project = project_queue.get(timeout=3)
            except queue.Empty:
                break

            pos = project["_position"]
            name = project.get("Project Name") or project["Project URL"]
            url = project["Project URL"]

            t0 = time.time()
            try:
                if not store.should_process(url):
                    cached = store.get_row(url)
                    if cached:
                        results[pos] = cached
                    done = prog.mark_done(0)
                    emit(f"PROGRESS:{_progress_msg(prog, name)}")
                    emit(f"[{done}/{prog.total}] Skip (cached): {name}")
                    collector.record_project({
                        "worker_id":       worker_id,
                        "project_name":    name,
                        "project_url":     url,
                        "status":          "cached",
                        "total_duration":  0.0,
                    })
                    continue

                row, stage_metrics = enrich_project(page, project)
                elapsed = time.time() - t0

                store.record(url, row)
                results[pos] = row

                done = prog.mark_done(elapsed)
                eta = prog.eta_seconds()
                eta_str = f"{int(eta // 60)}m{int(eta % 60)}s" if eta else "-"

                collector.record_project({
                    "worker_id":      worker_id,
                    "project_name":   name,
                    "project_url":    url,
                    "status":         "success",
                    "total_duration": round(elapsed, 3),
                    **stage_metrics,
                })

                emit(f"PROGRESS:{_progress_msg(prog, name)}")
                emit(
                    f"[{done}/{prog.total}] {name} | "
                    f"email={row['Official Email IDs']} | "
                    f"{elapsed:.1f}s | ETA {eta_str}"
                )
                logger.info(
                    "Enriched %s | pos=%d elapsed=%.1fs eta=%s",
                    name, pos, elapsed, eta_str,
                )

            except Exception as exc:
                elapsed = time.time() - t0
                logger.exception("Failed enriching %s: %s", name, exc)
                done = prog.mark_done(elapsed, failed=True)
                collector.record_project({
                    "worker_id":      worker_id,
                    "project_name":   name,
                    "project_url":    url,
                    "status":         "failed",
                    "total_duration": round(elapsed, 3),
                    "error":          str(exc),
                })
                emit(f"PROGRESS:{_progress_msg(prog, name)}")
                emit(f"[{done}/{prog.total}] Error: {name}: {exc}")
            finally:
                project_queue.task_done()

    finally:
        if ctx:
            try:
                ctx.close()
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


def run_pipeline(listing_url, emit=print, limit=None, mode="ranked", workers=DEFAULT_WORKERS):
    """Collect projects from a listing URL and enrich each into a lead row.

    Uses a thread pool so multiple projects are enriched concurrently.
    Each worker maintains its own browser process; `workers` controls how many
    run in parallel.  Results are re-assembled in original collection order so
    the exported CSV always respects newest-first / rank ordering.

    `emit` is called for every human-readable progress line and for structured
    PROGRESS:{...} JSON lines (consumed by the backend SSE layer).
    """
    _setup_logging()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    platform = detect_platform(listing_url)
    if not platform:
        raise ValueError(
            f"Unsupported platform URL. Supported: {', '.join(SUPPORTED_PLATFORMS)}"
        )

    run_id = uuid.uuid4().hex[:12]
    mode_label = "Recently Added" if mode == "recent" else "Top Ranked"
    emit(f"Platform detected: {platform}")
    emit(f"Mode: {mode_label}")
    emit(f"Run ID: {run_id}")
    emit(f"Collecting projects from: {listing_url}")

    t_collect_start = time.time()
    projects = collect_projects(listing_url, mode=mode)
    t_collect = time.time() - t_collect_start
    emit(f"Collected {len(projects)} projects in {t_collect:.1f}s.")

    if limit:
        projects = projects[:limit]
        emit(f"Limiting to {len(projects)} projects.")

    if not projects:
        emit("No projects to process.")
        return export_leads([], FINAL_CSV, FINAL_XLSX)

    # Assign stable position indices BEFORE any concurrent processing.
    # This index is the single source of truth for output ordering.
    for i, p in enumerate(projects):
        p["_position"] = i

    pd.DataFrame(projects).to_csv(PROJECTS_CSV, index=False)

    store = ResultsStore(STORE_PATH)
    total = len(projects)
    actual_workers = min(workers, total, 8)

    # Memory-aware cap: never launch more Chromium workers than the instance's
    # RAM can hold. Prevents OOM-kills on small cloud tiers (the run just uses
    # fewer workers and takes longer instead of crashing the backend).
    actual_workers, _mem_limit = _memory_safe_workers(actual_workers)
    if _mem_limit is not None and actual_workers < min(workers, total, 8):
        emit(
            f"Memory guard: capping to {actual_workers} worker(s) for "
            f"~{int(_mem_limit)} MB available "
            f"(each Chromium worker needs ~{_PER_WORKER_MB} MB)."
        )
        if _mem_limit < (_BASE_FOOTPRINT_MB + _PER_WORKER_MB):
            emit(
                "WARNING: this instance has very little memory; even one browser "
                "may be tight. Provision >= 2 GB RAM for reliable extraction."
            )

    collector = MetricsCollector(
        run_id=run_id,
        platform=platform,
        mode=mode,
        worker_count=actual_workers,
        requested=limit or total,
    )

    # Pre-populate results with any rows cached by a prior run so that a
    # resumed extraction after a crash re-includes them in the final export.
    results = {}  # int -> enriched row dict
    for p in projects:
        cached = store.get_row(p["Project URL"])
        if cached:
            results[p["_position"]] = cached
    cached_count = len(results)

    emit(
        f"Starting enrichment: {total} projects | {actual_workers} workers"
        + (f" | {cached_count} already cached" if cached_count else "")
    )

    project_queue = queue.Queue()
    for p in projects:
        project_queue.put(p)

    prog = _Progress(total, actual_workers)

    t_enrich_start = time.time()

    threads = [
        threading.Thread(
            target=_worker,
            args=(project_queue, results, prog, store, emit, collector, wid),
            daemon=True,
        )
        for wid in range(actual_workers)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    t_enrich_total = time.time() - t_enrich_start

    # Re-assemble in original collection order (position index).
    ordered_rows = [results[i] for i in range(total) if i in results]
    df = export_leads(ordered_rows, FINAL_CSV, FINAL_XLSX)

    emit(f"Exported {len(df)} leads -> {FINAL_CSV}")

    report = collector.finalize(
        t_collect=t_collect,
        t_enrich=t_enrich_total,
        collection_count=len(projects),
    )
    for line in collector.text_report(report).splitlines():
        emit(line)

    logger.info(
        "Benchmark | run_id=%s projects=%d successful=%d failed=%d workers=%d "
        "collect=%.1fs enrich=%.1fs total=%.1fs",
        run_id, total, report["successful"], report["failed"], actual_workers,
        t_collect, t_enrich_total, report["total_time_s"],
    )
    return df
