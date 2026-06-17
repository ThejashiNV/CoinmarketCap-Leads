"""
Thread-safe telemetry collector for the extraction pipeline.

Design:
  - MetricsCollector is instantiated once per run and shared across all worker
    threads.  Its _lock guards every mutation.
  - Each worker calls record_project() after enriching (or skipping) a project.
  - After all workers join, run_pipeline() calls finalize() which computes all
    aggregate statistics, persists two JSON files, and returns the full report.

Storage:
  output/metrics_latest.json   — full report for the most recent run
  output/metrics_history.json  — summary (no per-project rows) for last 20 runs
"""

import json
import os
import threading
import time
from datetime import datetime, timezone


OUTPUT_DIR = "output"
METRICS_LATEST  = os.path.join(OUTPUT_DIR, "metrics_latest.json")
METRICS_HISTORY = os.path.join(OUTPUT_DIR, "metrics_history.json")
MAX_HISTORY_RUNS = 20

# Canonical stage names (used as keys throughout the system).
STAGES = [
    "platform_page",
    "website_load",
    "contact_pages",
    "browser_fallback",
    "linkedin_recovery",
    "telegram_recovery",
    "email_recovery",
]

# Map stage name → project record key
STAGE_KEY = {
    "platform_page":     "t_platform",
    "website_load":      "t_website",
    "contact_pages":     "t_contact",
    "browser_fallback":  "t_browser_fallback",
    "linkedin_recovery": "t_linkedin_recovery",
    "telegram_recovery": "t_telegram_recovery",
    "email_recovery":    "t_email_recovery",
}

STAGE_LABEL = {
    "platform_page":     "Platform Page",
    "website_load":      "Website Load",
    "contact_pages":     "Contact Pages (HTTP)",
    "browser_fallback":  "Browser Fallback",
    "linkedin_recovery": "LinkedIn Recovery",
    "telegram_recovery": "Telegram Recovery",
    "email_recovery":    "Email Recovery",
}


# ── Utility helpers ────────────────────────────────────────────────────────────

def _pct(found: int, total: int) -> float:
    return round((found / total) * 100, 1) if total > 0 else 0.0


def _percentile(data: list, p: float) -> float:
    """p-th percentile (0–100) via linear interpolation, returns 0 on empty."""
    if not data:
        return 0.0
    s = sorted(data)
    idx = (p / 100.0) * (len(s) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (idx - lo), 2)


def _avg(values: list) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


def fmt_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def _atomic_write(path: str, data) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ── Main collector ─────────────────────────────────────────────────────────────

class MetricsCollector:
    """
    Accumulates per-project telemetry across concurrent worker threads and
    computes aggregate statistics when finalize() is called.

    Thread safety: all mutations guarded by self._lock.
    """

    def __init__(
        self,
        run_id: str,
        platform: str,
        mode: str,
        worker_count: int,
        requested: int,
    ):
        self._lock = threading.Lock()
        self.run_id     = run_id
        self.platform   = platform
        self.mode       = mode
        self.worker_count = worker_count
        self.requested  = requested
        self.t_start    = time.time()

        # Per-project records (dict per project).
        self._projects: list[dict] = []

        # Per-worker accumulators: worker_id → stats dict.
        self._workers: dict[int, dict] = {}

    # ── Public API ─────────────────────────────────────────────────────────────

    def record_project(self, record: dict) -> None:
        """Thread-safe: register one project's telemetry."""
        with self._lock:
            self._projects.append(record)

            wid = record.get("worker_id", 0)
            if wid not in self._workers:
                self._workers[wid] = {
                    "worker_id": wid,
                    "processed": 0,
                    "failed":    0,
                    "cached":    0,
                    "durations": [],
                    "stage_times": {s: [] for s in STAGES},
                }
            ws = self._workers[wid]
            status = record.get("status", "success")
            ws["processed"] += 1

            if status == "failed":
                ws["failed"] += 1
            elif status == "cached":
                ws["cached"] += 1

            dur = record.get("total_duration", 0.0)
            if dur > 0 and status not in ("cached",):
                ws["durations"].append(dur)

            if status == "success":
                for stage in STAGES:
                    v = record.get(STAGE_KEY[stage], 0.0)
                    if v and v > 0:
                        ws["stage_times"][stage].append(v)

    def finalize(
        self,
        t_collect: float,
        t_enrich: float,
        collection_count: int,
    ) -> dict:
        """
        Compute all aggregate stats, persist to disk, return full report dict.
        Call this once after all worker threads have joined.
        """
        with self._lock:
            projects = list(self._projects)
            workers  = dict(self._workers)

        total_time = t_collect + t_enrich

        active  = [p for p in projects if p.get("status") != "cached"]
        success = [p for p in active   if p.get("status") == "success"]
        failed  = [p for p in active   if p.get("status") == "failed"]
        cached  = [p for p in projects if p.get("status") == "cached"]

        durations = [p["total_duration"] for p in active if p.get("total_duration", 0) > 0]
        n_active  = len(active)

        # ── Stage average times ─────────────────────────────────────────────

        def _avg_stage(key: str) -> float:
            vals = [p.get(key, 0.0) for p in success if p.get(key, 0.0) > 0]
            return _avg(vals)

        stage_avgs = {stage: _avg_stage(STAGE_KEY[stage]) for stage in STAGES}

        # Bottleneck: stage with highest cumulative load across all projects.
        total_stage_s = sum(stage_avgs.values())
        if total_stage_s > 0:
            bottleneck = max(stage_avgs, key=stage_avgs.get)
            bottleneck_pct = _pct(int(stage_avgs[bottleneck] * n_active), int(total_stage_s * n_active))
        else:
            bottleneck = "unknown"
            bottleneck_pct = 0.0

        # ── Coverage ────────────────────────────────────────────────────────

        def _cov(field: str) -> float:
            return _pct(sum(1 for p in active if p.get(field, False)), n_active)

        # ── Recovery ────────────────────────────────────────────────────────

        recovery_invocations = sum(1 for p in active if p.get("recovery_used", False))
        recovery_successes   = sum(1 for p in active if p.get("recovery_success", False))

        # ── Per-worker summaries ─────────────────────────────────────────────

        worker_summaries = []
        for wid, ws in sorted(workers.items()):
            durs = ws["durations"]
            worker_summaries.append({
                "worker_id":         wid,
                "projects_processed": ws["processed"],
                "projects_successful": ws["processed"] - ws["failed"] - ws["cached"],
                "projects_failed":    ws["failed"],
                "projects_cached":    ws["cached"],
                "success_rate":       _pct(ws["processed"] - ws["failed"], ws["processed"]) if ws["processed"] else 0.0,
                "avg_duration_s":     _avg(durs),
                "min_duration_s":     round(min(durs), 2) if durs else 0.0,
                "max_duration_s":     round(max(durs), 2) if durs else 0.0,
                "median_duration_s":  _percentile(durs, 50),
                "stage_avg_times_s": {
                    stage: _avg(ws["stage_times"][stage])
                    for stage in STAGES
                },
            })

        # ── Full report ─────────────────────────────────────────────────────

        report = {
            # Identity
            "run_id":    self.run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "platform":  self.platform,
            "mode":      self.mode,
            "workers":   self.worker_count,
            "requested_leads": self.requested,

            # Counts
            "collection_count": collection_count,
            "total_processed":  n_active,
            "successful":       len(success),
            "failed":           len(failed),
            "cached":           len(cached),
            "success_rate":     _pct(len(success), n_active) if n_active else 0.0,

            # Timing
            "collection_time_s":  round(t_collect, 2),
            "enrichment_time_s":  round(t_enrich, 2),
            "total_time_s":       round(total_time, 2),
            "total_time_human":   fmt_duration(total_time),

            # Throughput
            "throughput_per_minute": round(n_active / (total_time / 60), 2)   if total_time > 0 else 0.0,
            "throughput_per_hour":   round(n_active / (total_time / 3600), 1) if total_time > 0 else 0.0,

            # Speed statistics
            "avg_project_time_s":    _avg(durations),
            "median_project_time_s": _percentile(durations, 50),
            "p95_project_time_s":    _percentile(durations, 95),
            "p99_project_time_s":    _percentile(durations, 99),
            "fastest_project_s":     round(min(durations), 2) if durations else 0.0,
            "slowest_project_s":     round(max(durations), 2) if durations else 0.0,

            # Stage breakdown
            "stage_avg_times_s":       stage_avgs,
            "stage_labels":            STAGE_LABEL,
            "biggest_bottleneck_stage": bottleneck,
            "biggest_bottleneck_label": STAGE_LABEL.get(bottleneck, bottleneck),
            "biggest_bottleneck_pct":   bottleneck_pct,

            # Coverage
            "website_coverage":  _cov("website_found"),
            "email_coverage":    _cov("email_found"),
            "linkedin_coverage": _cov("linkedin_found"),
            "telegram_coverage": _cov("telegram_found"),
            "twitter_coverage":  _cov("twitter_found"),
            "discord_coverage":  _cov("discord_found"),

            # Recovery
            "recovery_invocations":    recovery_invocations,
            "recovery_successes":      recovery_successes,
            "recovery_failures":       recovery_invocations - recovery_successes,
            "recovery_success_rate":   _pct(recovery_successes, recovery_invocations) if recovery_invocations else 0.0,

            # Per-worker breakdown
            "worker_metrics": worker_summaries,

            # Per-project detail (full rows)
            "projects": projects,
        }

        self._persist(report)
        return report

    def text_report(self, report: dict) -> str:
        """Return a human-readable benchmark report string."""
        r = report
        lines = [
            "═" * 58,
            "  EXTRACTION BENCHMARK REPORT",
            "═" * 58,
            f"  Run ID           : {r['run_id']}",
            f"  Platform         : {r['platform']}  ({r['mode']} mode)",
            f"  Workers          : {r['workers']}",
            "",
            f"  Requested Leads  : {r['requested_leads']}",
            f"  Collected        : {r['collection_count']}",
            f"  Successful       : {r['successful']}",
            f"  Failed           : {r['failed']}",
            f"  Cached (skipped) : {r['cached']}",
            f"  Success Rate     : {r['success_rate']}%",
            "",
            f"  Total Runtime    : {r['total_time_human']}",
            f"  Collection       : {r['collection_time_s']}s",
            f"  Enrichment       : {r['enrichment_time_s']}s",
            "",
            f"  Avg Time/Project : {r['avg_project_time_s']}s",
            f"  Median           : {r['median_project_time_s']}s",
            f"  p95              : {r['p95_project_time_s']}s",
            f"  Fastest          : {r['fastest_project_s']}s",
            f"  Slowest          : {r['slowest_project_s']}s",
            f"  Throughput       : {r['throughput_per_minute']} projects/min",
            "",
            "  Coverage",
            f"    Email     : {r['email_coverage']}%",
            f"    LinkedIn  : {r['linkedin_coverage']}%",
            f"    Telegram  : {r['telegram_coverage']}%",
            f"    Twitter   : {r['twitter_coverage']}%",
            "",
            "  Stage Averages (sec per project)",
        ]
        stage_avgs = r.get("stage_avg_times_s", {})
        bottleneck = r.get("biggest_bottleneck_stage", "")
        for stage in STAGES:
            t = stage_avgs.get(stage, 0.0)
            marker = "  ← BOTTLENECK" if stage == bottleneck else ""
            lines.append(f"    {STAGE_LABEL.get(stage, stage):<28}: {t:.1f}s{marker}")
        lines.append("")
        lines.append(f"  Biggest Bottleneck : {r['biggest_bottleneck_label']} ({r['biggest_bottleneck_pct']}%)")
        lines.append("═" * 58)
        return "\n".join(lines)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _persist(self, report: dict) -> None:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        _atomic_write(METRICS_LATEST, report)

        # History: store summary (without per-project rows) for last N runs.
        history = _load_history()
        summary = {k: v for k, v in report.items() if k != "projects"}
        history.insert(0, summary)
        history = history[:MAX_HISTORY_RUNS]
        _atomic_write(METRICS_HISTORY, history)


# ── Public loaders (used by backend_api.py) ────────────────────────────────────

def load_latest_metrics() -> dict | None:
    if not os.path.exists(METRICS_LATEST):
        return None
    try:
        with open(METRICS_LATEST, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _load_history() -> list:
    if not os.path.exists(METRICS_HISTORY):
        return []
    try:
        with open(METRICS_HISTORY, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def load_history() -> list:
    return _load_history()
