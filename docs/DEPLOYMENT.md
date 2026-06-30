# Deployment Guide

This guide covers deploying the **Crypto Lead Extraction Platform** to production. The
system has two independently-deployed components:

- **Backend** — FastAPI + Playwright (Chromium). Deploy as a Docker container (Render, Fly.io, a VM, or any container host).
- **Frontend** — React/Vite static site. Deploy to Vercel, Netlify, or any static host / nginx.

> See [`ENVIRONMENT.md`](ENVIRONMENT.md) for every environment variable, and
> [`PRODUCTION_CHECKLIST.md`](PRODUCTION_CHECKLIST.md) before you flip traffic on.

---

## 1. Backend

### Option A — Render (recommended, Blueprint)

The repo ships a [`render.yaml`](../render.yaml) Blueprint.

1. Push the repo to GitHub.
2. In Render: **New → Blueprint**, select the repo. Render reads `render.yaml`:
   - `runtime: docker`, `dockerfilePath: ./Dockerfile`
   - `healthCheckPath: /`
   - `plan: starter` (≥ 2 GB RAM recommended — Chromium is memory-heavy)
3. Click **Apply**. Render builds the image (installs Python deps + `playwright install --with-deps chromium`) and starts uvicorn.
4. Render injects `$PORT`; the container's `CMD` binds `0.0.0.0:$PORT`.
5. Wait for the health check (`GET /`) to go green. Note the public URL — you'll need it for the frontend.

### Option B — Render (manual)

**New → Web Service → Docker**, connect the repo. Render auto-detects the `Dockerfile`. Set the instance plan to ≥ 2 GB RAM. Health check path `/`.

### Option C — Self-hosted Docker

```bash
docker build -t crypto-leads-api .
docker run -d --name crypto-leads-api -p 8000:8000 crypto-leads-api
# Health check:
curl http://localhost:8000/
```

To bind a different port: `docker run -e PORT=9000 -p 9000:9000 ...`.

> **Single worker only.** Run exactly one uvicorn worker (the default `CMD`).
> Run state and SSE logs live in-process; multiple workers would split state.
> To scale, run one instance — do **not** raise the worker count.

---

## 2. Frontend

### Vercel (recommended)

1. **New Project**, import the repo.
2. Set **Root Directory** to `frontend`. Framework auto-detected as **Vite**.
3. Add an environment variable:
   - `VITE_API_BASE = https://<your-backend-host>` (the Render URL, **no trailing slash**)
4. Deploy. Vercel runs `npm install` + `npm run build` and serves `frontend/dist/`.

### Self-hosted (static / nginx)

```bash
cd frontend
VITE_API_BASE=https://<your-backend-host> npm run build
# Serve frontend/dist/ with any static server (nginx, caddy, S3+CloudFront…)
```

A ready-made [`frontend/Dockerfile`](../frontend/Dockerfile) builds the static
bundle and serves it via nginx:

```bash
cd frontend
docker build -t crypto-leads-web .
docker run -d -p 8080:80 crypto-leads-web   # http://localhost:8080
```

> `VITE_API_BASE` is baked in **at build time**. Changing the backend URL
> requires a rebuild/redeploy of the frontend.

---

## 3. Wire-up & verify

1. Confirm the backend health check returns `200`:
   `curl https://<backend-host>/` → `{"message":"Crypto Lead Enrichment API running", ...}`
2. Confirm CORS: the backend allows all origins (`allow_origins=["*"]`), so the
   Vercel domain works out of the box. Lock this down if you add auth.
3. Open the frontend, select a platform, and start a small extraction (Top 5).
4. Run the full [`POST_DEPLOY_VERIFICATION.md`](POST_DEPLOY_VERIFICATION.md) checklist.

---

## 4. Rollback

- **Render:** open the service → **Deploys** → pick the last-good deploy → **Redeploy**.
- **Self-hosted:** keep the previous image tag; `docker run` the prior tag.
- **Frontend (Vercel):** **Deployments → Promote** a previous build.

Both components are stateless (no database; `output/` is ephemeral working data),
so rollback is just redeploying a prior image/build.
