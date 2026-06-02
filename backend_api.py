import json
import os
import subprocess
import sys
import threading
import time

import pandas as pd
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from src.collectors.platforms.categories import collect_categories
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

# Maximum allowed extraction time (seconds). A Top-50 run takes ~17 min;
# 45 min gives ample headroom. If exceeded, the subprocess is killed so the
# server doesn't stay in "running" forever on a hung Chromium page.
MAX_RUN_SECONDS = 2700

# Maximum log entries kept in memory. A Top-50 run emits ~150-200 lines;
# 500 gives headroom without unbounded growth.
MAX_LOG_ENTRIES = 500

app = FastAPI(title="Crypto Lead Enrichment API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Shared run state. A single extraction runs at a time; logs are streamed to
# the frontend over SSE and terminated with a sentinel carrying done=True.
# `_state_lock` guards the check-and-set of `running` so two near-simultaneous
# /start-extraction requests can't both pass and spawn duplicate subprocesses.
state = {"running": False, "process": None}
live_logs = []
_state_lock = threading.Lock()


class ExtractionRequest(BaseModel):
    category_url: str
    top_n: int = 20


def _run_extraction(category_url, top_n):
    process = None
    try:
        env = dict(os.environ)
        env["LEAD_LIMIT"] = str(top_n)

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
            if line:
                # Cap log buffer to prevent unbounded memory growth.
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
        # Guarantee the subprocess is dead — prevents zombie Chromium.
        if process and process.poll() is None:
            try:
                process.kill()
                process.wait(timeout=10)
            except Exception:
                pass
        state["process"] = None
        state["running"] = False


@app.get("/")
def home():
    return {
        "message": "Crypto Lead Enrichment API running",
        "supported_platforms": SUPPORTED_PLATFORMS,
    }


@app.get("/categories")
def categories(url: str = ""):
    """Fetch every category from a platform's category-index URL."""
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
    top_n = max(1, min(top_n, 500))

    # Atomically claim the single run slot so concurrent requests can't race.
    with _state_lock:
        if state["running"]:
            return {"status": "busy", "message": "An extraction is already running."}
        state["running"] = True
        live_logs.clear()

    thread = threading.Thread(
        target=_run_extraction, args=(url, top_n), daemon=True
    )
    thread.start()

    return {"status": "started", "platform": platform, "top_n": top_n}


@app.get("/status")
def status():
    return {"running": state["running"], "log_count": len(live_logs)}


@app.get("/live-logs")
def stream_logs():
    def event_stream():
        index = 0
        idle_ticks = 0
        # Emit an initial comment so the client sees bytes immediately and
        # any proxy flushes the stream rather than buffering it.
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
                # Emit a heartbeat comment every ~10s so Cloudflare/proxies
                # don't close the idle connection. SSE comments are invisible
                # to EventSource (no onmessage).
                idle_ticks += 1
                if idle_ticks % 20 == 0:
                    yield ": keepalive\n\n"
                time.sleep(0.5)

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers=headers
    )


@app.get("/leads")
def get_leads():
    if not os.path.exists(LEADS_CSV):
        return []
    df = pd.read_csv(LEADS_CSV)
    return df.fillna("").to_dict(orient="records")


@app.get("/download/csv")
def download_csv():
    if not os.path.exists(LEADS_CSV):
        return {"status": "error", "message": "No leads file available yet."}
    return FileResponse(
        LEADS_CSV, media_type="text/csv", filename="crypto_leads.csv"
    )


@app.get("/download/xlsx")
def download_xlsx():
    if not os.path.exists(LEADS_XLSX):
        return {"status": "error", "message": "No XLSX file available yet."}
    return FileResponse(
        LEADS_XLSX,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="crypto_leads.xlsx",
    )
