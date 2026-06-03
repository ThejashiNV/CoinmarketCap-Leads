# Crypto Lead Extraction Platform

Multi-platform lead enrichment system that extracts contact information (emails, LinkedIn, Telegram, Twitter, Discord, GitHub) from crypto projects listed on CoinMarketCap, CoinGecko, and Coinranking.

## Architecture

```
Frontend (React 19 + Vite 8 + Tailwind v4)  -->  Vercel (static)
    |
    |  HTTPS (fetch / EventSource SSE)
    v
Backend (FastAPI + Playwright Chromium)      -->  Render / Docker
    |
    +-- Category collection (browser or HTTP)
    +-- Project listing (browser or API)
    +-- Per-project enrichment (browser + concurrent HTTP)
    +-- Search recovery (Brave / DuckDuckGo)
    +-- CSV / XLSX export
```

**Single-worker design.** One extraction runs at a time. State and logs are held in-process. The backend spawns `main.py` as a subprocess; progress is streamed to the frontend via SSE.

## Supported Platforms & Modes

| Platform       | Ranked (Top N by market cap) | Recently Added (Newest N) |
|----------------|------------------------------|---------------------------|
| CoinMarketCap  | Browser-based anchor parser  | `__NEXT_DATA__` JSON blob, sorted by `dateAdded` |
| CoinGecko      | Browser-based anchor parser  | `/recently_added` HTML page (global, no category filter) |
| Coinranking    | Browser-based anchor parser  | Public API `orderBy=listedAt` with `tags[]` filter |

## Output Schema (14 columns)

Project Name, Platform, Source URL, Project Page URL, Official Website URL, Official Email ID, Email Source, Email Confidence, LinkedIn URLs, Telegram URLs, Twitter URLs, Discord URLs, Github URLs, Missing Fields

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
LEAD_LIMIT=20 EXTRACT_MODE=recent python main.py "https://coinranking.com/coins/ai"
```

Output files are written to `output/final_leads.csv` and `output/final_leads.xlsx`.

## Environment Variables

### Backend (Render / Docker)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PORT`   | No       | `8000`  | Injected by Render automatically |

No API keys or secrets are required. The backend uses public web scraping only.

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

| Method | Path                | Description |
|--------|---------------------|-------------|
| GET    | `/`                 | Health check |
| GET    | `/capabilities`     | Platform mode support matrix |
| GET    | `/categories?url=`  | Fetch categories from a platform index URL |
| POST   | `/start-extraction` | Start extraction (body: `{category_url, top_n, mode}`) |
| GET    | `/status`           | Check if extraction is running |
| GET    | `/live-logs`        | SSE stream of extraction progress |
| GET    | `/leads`            | Get extracted leads as JSON |
| GET    | `/download/csv`     | Download leads as CSV |
| GET    | `/download/xlsx`    | Download leads as XLSX |

### POST /start-extraction Body

```json
{
  "category_url": "https://coinmarketcap.com/view/layer-1/",
  "top_n": 20,
  "mode": "ranked"
}
```

`mode` is `"ranked"` (top N by market cap) or `"recent"` (newest N by listing date).

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
├── backend_api.py                    # FastAPI application (9 endpoints)
├── main.py                           # CLI entry point (subprocess target)
├── requirements.txt                  # Python dependencies (11 packages)
├── Dockerfile                        # Backend container (python:3.12-slim + Chromium)
├── .dockerignore                     # Docker build exclusions
├── render.yaml                       # Render Blueprint
├── .gitignore
│
├── src/
│   ├── collectors/platforms/
│   │   ├── categories.py             # Category index scraper
│   │   └── listing.py                # Project listing collector (ranked + recent)
│   ├── enrichment/
│   │   ├── pipeline.py               # Orchestrator (collect -> enrich -> export)
│   │   ├── enricher.py               # Per-project 4-step enrichment
│   │   ├── platform_links.py         # Platform-specific link extraction
│   │   ├── store.py                  # Checkpoint store (resume on crash)
│   │   └── export.py                 # CSV/XLSX writer
│   └── scraping/
│       └── browser.py                # Playwright browser management
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

1. **Single concurrent extraction.** Only one extraction can run at a time. Concurrent `/start-extraction` requests return `{"status": "busy"}`.
2. **CoinGecko "Recently Added" is global.** CoinGecko does not expose per-category recently-added data. The mode returns the ~50 newest coins across all categories.
3. **CoinGecko "Recently Added" has no dates.** Coins are ordered by page position (newest first) but lack explicit `dateAdded` timestamps.
4. **Search recovery is rate-limited.** Brave and DuckDuckGo may throttle after ~20 queries. The circuit breaker backs off automatically; some LinkedIn/Telegram fields may remain empty on large runs.
5. **Extraction timeout.** Runs are killed after 45 minutes (`MAX_RUN_SECONDS = 2700`). A Top-50 run typically completes in ~17 minutes.
