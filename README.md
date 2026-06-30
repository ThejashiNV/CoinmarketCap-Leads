# Crypto Lead Extraction Platform

Multi-platform lead-generation system that discovers crypto projects and enriches each into a sales-ready lead — extracting website, business emails, founder details, and social profiles (LinkedIn, Telegram, Twitter/X, Discord, GitHub) from projects listed on **CoinMarketCap, CoinGecko, Coinranking, and DeFiLlama Raises**.

## Architecture

```
Frontend (React 19 + Vite 8 + Tailwind v4)  -->  Vercel (static)
    |
    |  HTTPS (fetch / EventSource SSE)
    v
Backend (FastAPI + Playwright Chromium)      -->  Render / Docker
    |
    +-- Collection
    |     +-- Category/listing collection (browser or HTTP)
    |     +-- Project listing (browser, public API, or __NEXT_DATA__)
    |
    +-- Per-project enrichment (Playwright + concurrent HTTP, N workers)
    |     +-- Seed pre-fill (DeFiLlama protocol metadata)
    |     +-- Official website crawl + contact-page harvest
    |     +-- Founder extraction
    |     +-- Search recovery (website / LinkedIn / Telegram / email /
    |         GitHub / founder) via Brave / Startpage / Yahoo / DuckDuckGo
    |
    +-- CSV / XLSX export + run telemetry
```

**Single-worker design.** One extraction runs at a time. Run state and logs are held in-process. The backend spawns `main.py` as a subprocess; progress is streamed to the frontend via Server-Sent Events (SSE). Within a run, enrichment is parallelized across N Playwright worker threads (each owns its own browser).

## Supported Platforms & Modes

Every platform supports two modes: **Ranked** and **Recent**.

| Platform       | Ranked                       | Recent                        | Categories |
|----------------|------------------------------|-------------------------------|-----------|
| CoinMarketCap  | Browser anchor parser (by market cap) | `__NEXT_DATA__` JSON, sorted by `dateAdded` | Yes (`/view/<slug>/`) |
| CoinGecko      | Browser anchor parser (by market cap) | `/recently_added` HTML page (global, no category filter) | Yes (`/en/categories/<slug>`) |
| Coinranking    | Browser anchor parser (by market cap) | Public API `orderBy=listedAt` with `tags[]` filter | Yes (`/coins/<slug>`) |
| DeFiLlama Raises | Funding rounds by amount raised | Funding rounds by date (newest) | No — fixed listing URL `https://defillama.com/raises` |

DeFiLlama is a **listing-only** platform: it has no category selection. The frontend auto-populates its fixed `https://defillama.com/raises` URL and the collector pulls all raises from the page's `__NEXT_DATA__` (no API key required), enriching protocol metadata from the free `api.llama.fi/protocols` endpoint.

## Output Schema (15 columns)

The CSV/XLSX export (`src/enrichment/export.py`) writes exactly these columns, in order:

| # | Column | # | Column |
|---|--------|---|--------|
| 1 | Company / Project Name | 9 | Discord URLs |
| 2 | Official Website URL | 10 | Founder Name |
| 3 | Official Email IDs | 11 | Founder LinkedIn |
| 4 | Contact Page URL | 12 | Industry / Category |
| 5 | LinkedIn URLs | 13 | Short Description |
| 6 | GitHub URLs | 14 | Source Platform |
| 7 | Twitter/X URLs | 15 | Discovery URL |
| 8 | Telegram URLs | | |

The `/leads` JSON API returns these columns **plus** two computed fields used by the dashboard: `_score` (0–100 lead-quality score) and `Missing Fields` (comma-separated list of empty mandatory fields). These computed fields are not written to the CSV/XLSX export.

## Local Development

### Prerequisites

- Python 3.10+
- Node.js 18+
- Git

### Backend Setup

```bash
git clone <repo-url>
cd CoinmarketCap-Leads

python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
playwright install --with-deps chromium

uvicorn backend_api:app --host 127.0.0.1 --port 8000
```

The API is now at `http://127.0.0.1:8000`. Health check: `GET /`.

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Opens at `http://localhost:5173`. The frontend defaults to `http://127.0.0.1:8000` as the API base.

### Running a CLI Extraction (No Frontend)

```bash
# Top 10 ranked projects from a CMC category
LEAD_LIMIT=10 EXTRACT_MODE=ranked python main.py "https://coinmarketcap.com/view/layer-1/"

# 20 most recently added projects from a Coinranking category
LEAD_LIMIT=20 EXTRACT_MODE=recent python main.py "https://coinranking.com/coins/new"

# 25 newest DeFiLlama funding rounds (listing-only, no category)
LEAD_LIMIT=25 EXTRACT_MODE=recent python main.py "https://defillama.com/raises"
```

Output files are written to `output/final_leads.csv` and `output/final_leads.xlsx`.

## Environment Variables

### Backend (Render / Docker)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PORT`   | No       | `8000`  | HTTP port for uvicorn. Injected automatically by Render. |

**No API keys or secrets are required.** The backend uses public web scraping only.

#### CLI-only variables (when running `main.py` directly)

These are set automatically by the backend when it spawns an extraction; you only set them yourself for the standalone CLI. See [`.env.example`](.env.example).

| Variable | Default | Description |
|----------|---------|-------------|
| `PLATFORM_URL` | — | Listing/category URL (alternative to passing it as the CLI argument) |
| `LEAD_LIMIT`   | all | Max number of leads to enrich |
| `EXTRACT_MODE` | `ranked` | `ranked` or `recent` |
| `WORKERS`      | `3` | Parallel enrichment workers (1–8) |

### Frontend (Vercel)

| Variable       | Required | Default                    | Description |
|----------------|----------|----------------------------|-------------|
| `VITE_API_BASE`| Yes (prod) | `http://127.0.0.1:8000` | Backend URL. Set in Vercel dashboard. No trailing slash. |

Set this in **Vercel > Project Settings > Environment Variables** before deploying.

## Production Deployment

### Backend on Render (Docker)

1. Create a new **Web Service** on Render.
2. Connect the repository.
3. Set **Runtime** to **Docker** (the `Dockerfile` and `render.yaml` handle the rest).
4. Render auto-detects `Dockerfile`, installs deps, installs Chromium, and starts uvicorn.
5. Health check is `GET /` (returns JSON).

Alternatively, use the Render Blueprint by importing `render.yaml`.

### Frontend on Vercel

1. Create a new project on Vercel.
2. Set **Root Directory** to `frontend`.
3. Framework is auto-detected as Vite.
4. Add environment variable: `VITE_API_BASE = https://<your-render-service>.onrender.com`
5. Deploy.

### Self-Hosted (Docker)

```bash
docker build -t crypto-leads-api .
docker run -p 8000:8000 crypto-leads-api
```

For the frontend, build and serve the static files:

```bash
cd frontend
npm run build
# Serve frontend/dist/ with any static file server (nginx, caddy, etc.)
```

## API Endpoints

| Method | Path                      | Description |
|--------|---------------------------|-------------|
| GET    | `/`                       | Health check (returns API status + supported platforms) |
| GET    | `/capabilities`           | Platform mode-support matrix (all platforms) |
| GET    | `/capabilities?platform=` | Capability descriptor for one platform |
| GET    | `/categories?url=`        | Fetch categories from a platform index URL |
| POST   | `/start-extraction`       | Start extraction (body: `{category_url, top_n, mode, workers}`) |
| GET    | `/status`                 | Running flag + progress (`done`/`total`/`pct`/`eta`) |
| GET    | `/live-logs`              | SSE stream of extraction progress |
| GET    | `/leads`                  | Completed leads as JSON (with `_score`, `Missing Fields`) |
| GET    | `/leads/partial`          | Partial leads mid-run (reads the incremental store) |
| GET    | `/download/csv`           | Download leads as CSV |
| GET    | `/download/xlsx`          | Download leads as XLSX |
| GET    | `/download/json`          | Download leads as JSON |
| GET    | `/metrics`                | Latest run telemetry (success rate, timings, per-field coverage) |
| GET    | `/metrics/history`        | Telemetry for past runs |
| GET    | `/metrics/export/json`    | Download latest metrics as JSON |
| GET    | `/metrics/export/csv`     | Download per-project metrics as CSV |

### POST /start-extraction Body

```json
{
  "category_url": "https://coinmarketcap.com/view/layer-1/",
  "top_n": 20,
  "mode": "ranked",
  "workers": 3
}
```

- `category_url` — a category/listing URL for CMC/CoinGecko/Coinranking, or `https://defillama.com/raises` for DeFiLlama.
- `top_n` — number of leads (clamped 1–1000).
- `mode` — `"ranked"` (top N by market cap / amount raised) or `"recent"` (newest N).
- `workers` — parallel enrichment workers (clamped 1–8, default 3).

Returns `{"status": "started", ...}`, or `{"status": "busy"}` if a run is already in progress.

## Recommended Server Specifications

| Tier | RAM | CPU | Suitable For |
|------|-----|-----|-------------|
| Minimum | 1 GB | 1 vCPU | Top 10 extractions |
| Recommended | 2 GB | 1 vCPU | Top 50 extractions |
| Production | 4 GB | 2 vCPU | Top 100+ extractions |

Chromium headless is the main memory consumer. Each enrichment run uses a single browser instance reused across all projects.

## Project Structure

```
CoinmarketCap-Leads/
├── backend_api.py                    # FastAPI application (15 endpoints)
├── main.py                           # CLI entry point (subprocess target)
├── requirements.txt                  # Python dependencies
├── Dockerfile                        # Backend container (python:3.12-slim + Chromium)
├── .dockerignore                     # Docker build exclusions
├── render.yaml                       # Render Blueprint
├── .env.example                      # Backend environment variable template
├── .gitignore
│
├── docs/                             # Deployment & operations documentation
│   ├── DEPLOYMENT.md                 # Step-by-step deployment guide
│   ├── ENVIRONMENT.md                # Environment variable reference
│   ├── PRODUCTION_CHECKLIST.md       # Pre-deploy checklist
│   ├── POST_DEPLOY_VERIFICATION.md   # Post-deploy smoke tests
│   └── RUNBOOK.md                    # Operations / monitoring / troubleshooting
│
├── src/
│   ├── collectors/platforms/
│   │   ├── categories.py             # Category index scraper
│   │   ├── listing.py                # Project listing collector (ranked + recent)
│   │   └── defillama.py              # DeFiLlama Raises collector (page + protocols API)
│   ├── enrichment/
│   │   ├── pipeline.py               # Orchestrator (collect -> enrich -> export), N workers
│   │   ├── enricher.py               # Per-project multi-source enrichment
│   │   ├── platform_links.py         # Platform-specific link extraction
│   │   ├── store.py                  # Checkpoint store (resume on crash)
│   │   └── export.py                 # CSV/XLSX writer (canonical 15-column schema)
│   ├── scraping/
│   │   └── browser.py                # Playwright browser management
│   └── telemetry/
│       └── collector.py              # Per-run metrics collection + reports
│
├── utils/
│   ├── email_tools.py                # Email extraction, scoring, multi-email output
│   ├── social_tools.py               # LinkedIn/Telegram/Twitter/Discord/GitHub extraction
│   ├── search_recovery.py            # Web search fallback for missing socials
│   ├── website_validator.py          # Official website validation + blocklists
│   ├── url_tools.py                  # URL normalization and deduplication
│   ├── text_tools.py                 # Project name cleanup
│   └── platform_detector.py          # Platform URL detection
│
└── frontend/
    ├── vercel.json                   # Vercel deployment config
    ├── .env.example                  # Environment variable template
    ├── package.json                  # Node dependencies
    ├── vite.config.js                # Vite + Tailwind config
    ├── index.html                    # HTML entry point
    └── src/
        ├── App.jsx                   # Main React component (single-file dashboard)
        ├── main.jsx                  # React DOM mount
        └── index.css                 # Tailwind + custom animations
```

## Known Limitations

These are **data/design limitations, not software defects.** The enricher deliberately returns `N/A` rather than attaching unverified data, which keeps lead quality high at the cost of some empty fields.

1. **Single concurrent extraction.** Only one extraction can run at a time. Concurrent `/start-extraction` requests return `{"status": "busy"}`. (Run state and SSE logs are held in-process, so the backend must run as a single uvicorn worker.)
2. **CoinGecko "Recently Added" is global.** CoinGecko does not expose per-category recently-added data; the mode returns the ~50 newest coins across all categories, without `dateAdded` timestamps.
3. **Search recovery is rate-limited.** Public search engines (Brave / Startpage / Yahoo / DuckDuckGo) may throttle after a burst of queries. A circuit breaker backs off automatically and falls across engines; some LinkedIn/Telegram/email fields may remain empty on large back-to-back runs.
4. **DeFiLlama coverage is lower than the token platforms.** `defillama.com/raises` lists *funding rounds* — including pre-launch/stealth startups and non-crypto companies — many of which have minimal public web presence at the time of their raise. Token-listing platforms (CMC/CoinGecko/Coinranking) list *traded coins* that always have a website, socials, and market page, so they enrich far more completely.
5. **Founder LinkedIn is frequently empty.** Crypto founders are often pseudonymous or not on LinkedIn. The recovery is conservative (a profile is accepted only when its slug matches the founder's name) to avoid attaching the wrong person; it returns results only when a clearly-matching public profile exists.
6. **Extraction timeout.** Runs are killed after 45 minutes (`MAX_RUN_SECONDS = 2700`). A Top-50 run typically completes in ~17 minutes; large fresh runs are slower due to per-project website crawling and search recovery.

## Troubleshooting

| Symptom | Likely cause | Resolution |
|---------|--------------|------------|
| `{"status":"busy"}` on start | A run is already in progress | Wait for it to finish (`GET /status`) or restart the service to clear state |
| `Unsupported URL` error | URL is not a CMC/CoinGecko/Coinranking/DeFiLlama domain | Use a supported platform URL; for DeFiLlama use exactly `https://defillama.com/raises` |
| `No categories found` | The URL is a coin/protocol page, not a category index | Pass the category **index** URL (e.g. `https://coinmarketcap.com/cryptocurrency-category/`) |
| Browser launch fails on a PaaS | Chromium or its OS deps missing | Ensure the image was built with `playwright install --with-deps chromium` (the provided `Dockerfile` does this) |
| Many empty LinkedIn/Telegram fields on a large run | Search engines throttling | Reduce `top_n`, lower `workers`, or wait a few minutes between runs |
| `/download/csv` returns "No leads file available yet" | No extraction has completed | Run an extraction first; downloads read `output/final_leads.csv` |
| Frontend shows network errors | `VITE_API_BASE` not pointing at the live backend | Set `VITE_API_BASE` to the HTTPS backend URL (no trailing slash) and rebuild |

For deployment and operations details, see the [`docs/`](docs/) directory.
