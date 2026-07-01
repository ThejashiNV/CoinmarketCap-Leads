# Operations Runbook

Operational reference for running, monitoring, and troubleshooting the
**Crypto Lead Extraction Platform** in production.

---

## 1. Service model

- **Backend:** single Docker container, FastAPI + Playwright (Chromium), **one uvicorn worker**.
- **Frontend:** static bundle (Vercel/nginx), no server logic.
- **State:** none persisted. Run state and SSE logs are **in-process**; results
  are written to `output/` (ephemeral) inside the container. A restart clears all
  of it. There is **no database**.
- **Concurrency:** exactly one extraction at a time. A second `/start-extraction`
  while a run is active returns `{"status":"busy"}`.

---

## 2. Health & monitoring

| Signal | How | Healthy |
|--------|-----|---------|
| Liveness | `GET /` | `200` JSON with 4 platforms |
| Run state | `GET /status` | `running` bool + progress object |
| Last-run quality | `GET /metrics` | success rate, timings, coverage |
| Logs | platform dashboard / `docker logs <container>` | uvicorn access lines, no tracebacks |

**Recommended external monitor:** HTTP check on `GET /` every 60 s (this is also
the Render health-check path). Alert if non-200 for > 2 min.

**Memory:** Chromium is the main consumer. Each worker ≈ 200–300 MB. With the
default 3 workers, expect ~1–1.5 GB peak during a run. Provision **≥ 2 GB**.

---

## 3. Routine operations

### Start an extraction (API)
```bash
curl -X POST $API/start-extraction -H 'Content-Type: application/json' \
  -d '{"category_url":"https://defillama.com/raises","top_n":25,"mode":"recent","workers":3}'
```

### Watch progress
```bash
curl $API/status            # poll
curl -N $API/live-logs      # stream SSE
```

### Retrieve results
```bash
curl -o leads.csv  $API/download/csv
curl -o leads.xlsx $API/download/xlsx
curl      $API/leads        # JSON (with _score, Missing Fields)
```

### Stop / reset a stuck run
There is no stop endpoint by design (single-run model). To clear a run:
**restart the service** (Render: Manual Deploy → *Restart*, or `docker restart`).
A run also self-terminates at `MAX_RUN_SECONDS` (45 min).

---

## 4. Sizing & tuning

> **Minimum RAM: 2 GB** (Render **Standard** or larger). The 512 MB Free/Starter
> tiers OOM-crash mid-run. Chromium needs ~350 MB per worker on top of a ~300 MB
> base, so even one worker needs roughly 1 GB to be safe.

| Instance RAM | Effective workers* | Suitable for |
|--------------|--------------------|--------------|
| 512 MB | 1 (will likely still OOM) | ❌ not viable |
| 1 GB | 1–2 | Top 10 |
| 2 GB | up to 3 | Top 50 |
| 4 GB | up to 8 | Top 100+ |

\* **Automatic memory guard.** The pipeline detects the instance's memory limit
(cgroup-aware) and **caps the worker count to fit RAM**, regardless of what the
UI requests. If you ask for 3 workers on a 1 GB box it silently runs 1–2 and
logs `Memory guard: capping to N worker(s)…`. This prevents OOM crashes — the run
is slower, not dead. It cannot rescue a < ~1 GB instance, which is too small for
even one browser.

- More workers = faster but more RAM and more search-engine throttling.
- Lower `workers` and `top_n` if you see OOM kills or heavy throttling.

---

## 5. Troubleshooting

| Symptom | Cause | Action |
|---------|-------|--------|
| **UI: "Lost connection to server" + progress frozen at low %** | Historically caused by the frontend depending on the long-lived SSE stream (`/live-logs`), which some hosting networks drop repeatedly even though the backend is healthy. **Fixed:** the UI now polls `GET /logs?since=` for progress/logs/completion and no longer relies on SSE. If you still see this message, the backend is genuinely unreachable (crashed, OOM, or stopped). | First confirm the backend: `curl $API/` and `curl $API/status`. If those succeed, the UI will recover on its own (it only shows this after ~8 s of failed polls). If they fail, check `docker logs` for a restart / OOM and ensure ≥ 2 GB RAM. |
| `502/503` right after deploy | Container still building/starting Chromium | Wait for health check; first boot is slower |
| `GET /` non-200 | Backend crashed or OOM | Check `docker logs`; increase RAM; restart |
| Run stuck at `running:true` | Long/blocked enrichment | Wait (auto-kill at 45 min) or restart service |
| `{"status":"busy"}` | A run is already active | Wait for it, or restart to force-clear |
| Browser launch failed | Chromium/OS deps missing | Rebuild image with `playwright install --with-deps chromium` (the `Dockerfile` already does this) |
| Empty LinkedIn/Telegram/email on many rows | Search engines throttling | Lower `workers`/`top_n`; space out runs; this is expected on large back-to-back runs |
| DeFiLlama rows sparse | Data limitation (pre-launch/stealth raises) | Expected — see README *Known Limitations* #4; not a bug |
| `download/*` returns "No leads file available yet" | No run has completed since last restart | Run an extraction first |
| Frontend can't reach API | `VITE_API_BASE` wrong or CORS | Verify build-time `VITE_API_BASE`; CORS is `*` by default |

### Reading logs
- Structured progress lines: `PROGRESS:{...}` (JSON, parsed for the progress bar).
- Per-project lines: `[done/total] <name> | email=… | <elapsed>s | ETA …`.
- A genuine failure prints `Error: <name>: <exc>` for that project but the run
  continues; the run only aborts on `PIPELINE FAILED`.

---

## 6. Known-safe noise (not incidents)

- `search recovery (ddg) failed: … timed out` — one search engine throttled; the
  multi-engine fallback handles it. Not an error.
- `fetch failed … ERR_CERT_COMMON_NAME_INVALID` — a target project's own site has
  a bad TLS cert; that project's website crawl is skipped gracefully.
- `debconf: … frontend is not usable` — appears only in the Docker **build** logs
  (apt during `playwright install`); harmless.

---

## 7. Backup & data retention

Nothing to back up. `output/*.csv/.xlsx/.json` are regenerated each run and are
ephemeral. If you need to retain leads, download them after each run (CSV/XLSX/JSON
endpoints) and store them externally.

---

## 8. Dependencies & updates

- **Python:** see [`requirements.txt`](../requirements.txt). Pinning is open
  (latest compatible). To freeze, pin versions and rebuild.
- **Chromium:** installed by Playwright at image build; tied to the installed
  `playwright` version. Rebuild the image to update.
- **Frontend:** see [`frontend/package.json`](../frontend/package.json).
- After any dependency bump: rebuild both images and re-run
  [`POST_DEPLOY_VERIFICATION.md`](POST_DEPLOY_VERIFICATION.md).
