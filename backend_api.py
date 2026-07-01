import json
import os
import subprocess
import sys
import threading
import time

import pandas as pd
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from src.collectors.platforms.categories import collect_categories
from src.enrichment.pipeline import DEFAULT_WORKERS
from src.telemetry.collector import load_latest_metrics, load_history
from utils.platform_detector import (
    detect_platform,
    is_category_url,
    SUPPORTED_PLATFORMS,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_SCRIPT = os.path.join(BASE_DIR, "main.py")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
LEADS_CSV = os.path.join(OUTPUT_DIR, "final_leads.csv")
LEADS_XLSX = os.path.join(OUTPUT_DIR, "final_leads.xlsx")
STORE_PATH = os.path.join(OUTPUT_DIR, "enrich_results.json")
METRICS_LATEST_PATH = os.path.join(OUTPUT_DIR, "metrics_latest.json")

# Hard cap on a single extraction run (45 min).
MAX_RUN_SECONDS = 2700
# Log buffer size — capped so memory doesn't grow unbounded on very large runs.
MAX_LOG_ENTRIES = 1000

app = FastAPI(title="Crypto Lead Enrichment API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Shared run state ──────────────────────────────────────────────────────────
# A single extraction runs at a time.  `_state_lock` makes the check-and-set
# of `running` atomic so two near-simultaneous POST /start-extraction requests
# can't both pass and spawn duplicate subprocesses.

state = {
    "running": False,
    "process": None,
    "progress": {
        "done": 0,
        "total": 0,
        "pct": 0.0,
        "project": "",
        "eta": 0,
        "workers": 0,
    },
}
live_logs: list[dict] = []
_state_lock = threading.Lock()


class ExtractionRequest(BaseModel):
    category_url: str
    top_n: int = 20
    mode: str = "ranked"   # "ranked" | "recent"
    workers: int = DEFAULT_WORKERS


def _run_extraction(category_url: str, top_n: int, mode: str, workers: int):
    process = None
    try:
        env = dict(os.environ)
        env["LEAD_LIMIT"] = str(top_n)
        env["EXTRACT_MODE"] = mode
        env["WORKERS"] = str(max(1, min(workers, 8)))

        process = subprocess.Popen(
            [sys.executable, MAIN_SCRIPT, category_url],
            cwd=BASE_DIR,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        state["process"] = process

        deadline = time.time() + MAX_RUN_SECONDS
        for line in process.stdout:
            line = line.rstrip()
            if not line:
                continue

            # Structured progress line emitted by the pipeline.
            if line.startswith("PROGRESS:"):
                try:
                    data = json.loads(line[9:])
                    state["progress"].update(data)
                    # Also push as typed SSE event so the frontend can update
                    # its progress bar without parsing log text.
                    if len(live_logs) < MAX_LOG_ENTRIES:
                        live_logs.append({"type": "progress", **data})
                except Exception:
                    pass
                continue

            if len(live_logs) < MAX_LOG_ENTRIES:
                live_logs.append({"message": line})

            if time.time() > deadline:
                live_logs.append({
                    "message": f"Extraction timed out after {MAX_RUN_SECONDS}s.",
                    "done": True,
                })
                process.kill()
                return

        process.wait(timeout=30)
        live_logs.append({"message": "Extraction finished.", "done": True})

    except Exception as exc:
        live_logs.append({"message": f"Extraction error: {exc}", "done": True})
    finally:
        if process and process.poll() is None:
            try:
                process.kill()
                process.wait(timeout=10)
            except Exception:
                pass
        state["process"] = None
        state["running"] = False


# ── Platform capability matrix ────────────────────────────────────────────────

PLATFORM_CAPABILITIES = {
    "coinmarketcap": {
        "platform": "CoinMarketCap",
        "supports_ranked": True,
        "supports_recent": True,
        "supports_category_recent": True,
        "supports_date_filter": True,
        "recent_source": "Category page __NEXT_DATA__ (dateAdded field)",
    },
    "coingecko": {
        "platform": "CoinGecko",
        "supports_ranked": True,
        "supports_recent": True,
        "supports_category_recent": False,
        "supports_date_filter": False,
        "recent_source": "Global /recently_added page (no category filter, no dates)",
    },
    "coinranking": {
        "platform": "Coinranking",
        "supports_ranked": True,
        "supports_recent": True,
        "supports_category_recent": True,
        "supports_date_filter": True,
        "recent_source": "Public API (orderBy=listedAt, tags[] filter)",
    },
    "defillama": {
        "platform": "DeFiLlama Raises",
        "supports_ranked": True,
        "supports_recent": True,
        "supports_category_recent": False,
        "supports_date_filter": True,
        "recent_source": "DeFiLlama Raises API (api.llama.fi/raises, newest first)",
        "listing_url": "https://defillama.com/raises",
        "listing_type": "raises",
        "requires_category_url": False,
    },
}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/")
def home():
    return {
        "message": "Crypto Lead Enrichment API running",
        "supported_platforms": SUPPORTED_PLATFORMS,
    }


@app.get("/capabilities")
def capabilities(platform: str = ""):
    if platform:
        key = platform.strip().lower()
        info = PLATFORM_CAPABILITIES.get(key)
        if info:
            return info
        return {"status": "error", "message": f"Unknown platform: {platform}"}
    return {"platforms": list(PLATFORM_CAPABILITIES.values())}


@app.get("/categories")
def categories(url: str = ""):
    url = (url or "").strip()
    if not url:
        return {"status": "error", "message": "A category URL is required."}

    platform = detect_platform(url)
    if not platform:
        return {
            "status": "error",
            "message": f"Unsupported URL. Supported platforms: {', '.join(SUPPORTED_PLATFORMS)}",
        }

    if not is_category_url(url):
        return {
            "status": "error",
            "message": (
                "URL must be a CATEGORY listing page "
                "(e.g. https://coinmarketcap.com/cryptocurrency-category/)."
            ),
        }

    try:
        found = collect_categories(url)
    except Exception as exc:
        return {"status": "error", "message": f"Could not load categories: {exc}"}

    if not found:
        return {
            "status": "error",
            "message": "No categories found at that URL. Check the category listing link.",
        }

    return {"status": "ok", "platform": platform, "categories": found}


@app.post("/start-extraction")
def start_extraction(payload: ExtractionRequest):
    url = (payload.category_url or "").strip()
    if not url:
        return {"status": "error", "message": "A category URL is required."}

    platform = detect_platform(url)
    if not platform:
        return {
            "status": "error",
            "message": f"Unsupported URL. Supported platforms: {', '.join(SUPPORTED_PLATFORMS)}",
        }

    try:
        top_n = int(payload.top_n)
    except (TypeError, ValueError):
        top_n = 20
    top_n = max(1, min(top_n, 1000))

    mode = (payload.mode or "ranked").strip().lower()
    if mode not in ("ranked", "recent"):
        mode = "ranked"

    workers = max(1, min(int(payload.workers or DEFAULT_WORKERS), 8))

    with _state_lock:
        if state["running"]:
            return {"status": "busy", "message": "An extraction is already running."}
        state["running"] = True
        state["progress"] = {
            "done": 0, "total": top_n, "pct": 0.0,
            "project": "", "eta": 0, "workers": workers,
        }
        live_logs.clear()

    thread = threading.Thread(
        target=_run_extraction, args=(url, top_n, mode, workers), daemon=True
    )
    thread.start()

    return {"status": "started", "platform": platform, "top_n": top_n, "workers": workers}


@app.get("/status")
def status():
    return {
        "running": state["running"],
        "log_count": len(live_logs),
        "progress": state["progress"],
    }


@app.get("/logs")
def get_logs(since: int = 0):
    """Poll-friendly log tail (a reliable alternative to the SSE stream).

    Returns log entries added since the `since` cursor, plus the current
    `running` flag and `progress`, so the frontend can drive the whole UI by
    polling a single endpoint. This avoids depending on a long-lived SSE
    connection, which some hosting networks drop repeatedly.
    """
    try:
        since = max(0, int(since))
    except (TypeError, ValueError):
        since = 0
    total = len(live_logs)
    new = live_logs[since:total] if since < total else []
    return {
        "logs": new,
        "next": total,
        "running": state["running"],
        "progress": state["progress"],
    }


@app.get("/live-logs")
def stream_logs():
    def event_stream():
        index = 0
        idle_ticks = 0
        yield ": connected\n\n"
        while True:
            if index < len(live_logs):
                item = live_logs[index]
                index += 1
                idle_ticks = 0
                yield f"data: {json.dumps(item)}\n\n"
                if item.get("done"):
                    return
            elif not state["running"]:
                yield f"data: {json.dumps({'message': 'idle', 'done': True})}\n\n"
                return
            else:
                idle_ticks += 1
                if idle_ticks % 20 == 0:
                    yield ": keepalive\n\n"
                time.sleep(0.5)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


_MANDATORY = [
    "Official Website URL",
    "Official Email IDs",
    "LinkedIn URLs",
    "Telegram URLs",
]

def _enrich_record(record: dict) -> dict:
    """Add computed fields (_score, Missing Fields) that the frontend expects."""
    found = sum(
        1 for f in _MANDATORY
        if record.get(f, "").strip() not in ("", "N/A")
    )
    record["_score"] = round((found / len(_MANDATORY)) * 100)
    missing = [f for f in _MANDATORY if record.get(f, "").strip() in ("", "N/A")]
    record["Missing Fields"] = ", ".join(missing) if missing else ""
    return record


@app.get("/leads")
def get_leads():
    if not os.path.exists(LEADS_CSV):
        return []
    try:
        df = pd.read_csv(LEADS_CSV)
        records = df.fillna("").to_dict(orient="records")
        return [_enrich_record(r) for r in records]
    except Exception:
        return []


@app.get("/leads/partial")
def get_leads_partial():
    """Return whatever has been enriched so far, even mid-extraction.

    Reads directly from the incremental store (enrich_results.json) so the
    frontend can show live results while the pipeline is still running.
    Falls back to final_leads.csv if the store is absent.
    """
    rows = []
    if os.path.exists(STORE_PATH):
        try:
            with open(STORE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                rows = [
                    entry["row"]
                    for entry in data.values()
                    if isinstance(entry, dict) and "row" in entry
                ]
        except Exception:
            pass
    if not rows and os.path.exists(LEADS_CSV):
        try:
            import pandas as _pd
            df = _pd.read_csv(LEADS_CSV)
            rows = df.fillna("").to_dict(orient="records")
        except Exception:
            pass
    return [_enrich_record(r) for r in rows]


@app.get("/download/csv")
def download_csv():
    if not os.path.exists(LEADS_CSV):
        return {"status": "error", "message": "No leads file available yet."}
    return FileResponse(LEADS_CSV, media_type="text/csv", filename="crypto_leads.csv")


@app.get("/download/xlsx")
def download_xlsx():
    if not os.path.exists(LEADS_XLSX):
        return {"status": "error", "message": "No XLSX file available yet."}
    return FileResponse(
        LEADS_XLSX,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="crypto_leads.xlsx",
    )


@app.get("/download/json")
def download_json():
    if not os.path.exists(LEADS_CSV):
        return {"status": "error", "message": "No leads file available yet."}
    try:
        df = pd.read_csv(LEADS_CSV)
        records = df.fillna("").to_dict(orient="records")
        content = json.dumps(records, ensure_ascii=False, indent=2)
        return StreamingResponse(
            iter([content]),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="crypto_leads.json"'},
        )
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@app.get("/metrics")
def get_metrics():
    data = load_latest_metrics()
    if data is None:
        return JSONResponse(
            status_code=404,
            content={"status": "not_found", "message": "No metrics available yet. Run an extraction first."},
        )
    return data


@app.get("/metrics/history")
def get_metrics_history():
    return load_history()


@app.get("/metrics/export/json")
def export_metrics_json():
    if not os.path.exists(METRICS_LATEST_PATH):
        return JSONResponse(
            status_code=404,
            content={"status": "not_found", "message": "No metrics file available yet."},
        )
    return FileResponse(
        METRICS_LATEST_PATH,
        media_type="application/json",
        filename="metrics_latest.json",
    )


@app.get("/metrics/export/csv")
def export_metrics_csv():
    data = load_latest_metrics()
    if data is None:
        return JSONResponse(
            status_code=404,
            content={"status": "not_found", "message": "No metrics available yet."},
        )
    try:
        projects = data.get("projects", [])
        if not projects:
            return JSONResponse(
                status_code=404,
                content={"status": "not_found", "message": "No per-project data in metrics."},
            )
        df = pd.json_normalize(projects)
        content = df.to_csv(index=False)
        return StreamingResponse(
            iter([content]),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="metrics_projects.csv"'},
        )
    except Exception as exc:
        return {"status": "error", "message": str(exc)}
