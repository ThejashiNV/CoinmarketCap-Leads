# Environment Variable Reference

**No secrets, API keys, or credentials are used anywhere in this project.** The
backend performs only public web scraping. Nothing in this reference is sensitive.

Templates: [`.env.example`](../.env.example) (backend) and
[`frontend/.env.example`](../frontend/.env.example) (frontend).

---

## Backend

| Variable | Scope | Required | Default | Description |
|----------|-------|----------|---------|-------------|
| `PORT` | Server | No | `8000` | HTTP port uvicorn binds. Injected automatically by Render. Set manually only for local/self-hosted. |

### CLI-only variables

Set automatically by the backend when it spawns the extraction subprocess
(`backend_api.py` → `main.py`). You only set these when running `main.py` yourself.

| Variable | Required | Default | Valid values | Description |
|----------|----------|---------|--------------|-------------|
| `PLATFORM_URL` | No* | — | a supported listing/category URL | Listing URL to extract from. Alternative to passing it as `argv[1]`. *Required if no CLI argument is given. |
| `LEAD_LIMIT` | No | all | positive integer | Max leads to enrich. Blank = all collected projects. |
| `EXTRACT_MODE` | No | `ranked` | `ranked`, `recent` | Ranking (market cap / amount raised) vs newest-first. |
| `WORKERS` | No | `3` | `1`–`8` | Parallel enrichment workers; each runs its own Chromium (~200–300 MB RAM). |

---

## Frontend

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `VITE_API_BASE` | Yes (prod) | `http://127.0.0.1:8000` | HTTPS URL of the backend, **no trailing slash**. Baked in at build time — changing it requires a rebuild. |

---

## Internal constants (not env vars)

Tunable only by editing source — documented here for operators.

| Constant | File | Value | Meaning |
|----------|------|-------|---------|
| `MAX_RUN_SECONDS` | `backend_api.py` | `2700` (45 min) | Hard cap per extraction; the run is killed past this. |
| `MAX_LOG_ENTRIES` | `backend_api.py` | `1000` | SSE log buffer cap (bounds memory on large runs). |
| `DEFAULT_WORKERS` | `src/enrichment/pipeline.py` | `3` | Default parallel workers if unspecified. |

---

## Notes

- `python-dotenv` is installed but the backend does **not** auto-load a `.env`
  file in production (env vars come from the platform). A local `.env` is for
  developer convenience only and is gitignored.
- CORS is wide-open (`allow_origins=["*"]`) so any frontend origin works. If you
  later add authentication, restrict origins in `backend_api.py`.
