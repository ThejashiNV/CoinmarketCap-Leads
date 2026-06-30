# Production Checklist

Complete before promoting a build to production.

## Code & repository
- [ ] `git status` is clean; working on the intended commit of `main`.
- [ ] No secrets/keys committed (project uses none — verify none were added).
- [ ] `.gitignore` excludes `output/`, `logs/`, `.env`, `venv/`, `node_modules/`, `dist/`.
- [ ] `python -m compileall backend_api.py main.py src utils` succeeds.
- [ ] All modules import cleanly (no broken imports).

## Backend image
- [ ] `docker build -t crypto-leads-api .` completes with exit 0.
- [ ] Image runs: `docker run -p 8000:8000 crypto-leads-api` and `GET /` returns 200.
- [ ] Chromium launches inside the container (bundled, via `playwright install --with-deps chromium`).
- [ ] Instance has **≥ 2 GB RAM** (Chromium is the main memory consumer).
- [ ] Exactly **one** uvicorn worker (in-process run state).

## Frontend build
- [ ] `npm install` + `npm run build` succeed with no errors.
- [ ] `VITE_API_BASE` points at the production backend (HTTPS, no trailing slash).
- [ ] Static bundle (`frontend/dist/`) deployed.

## Configuration
- [ ] Backend `PORT` handled (injected by Render, or set for self-host).
- [ ] Health check path configured to `/`.
- [ ] CORS acceptable for your setup (currently `*` — fine for a public tool).
- [ ] `render.yaml` (if used) points at `./Dockerfile`, `healthCheckPath: /`.

## Functional smoke (post-build, pre-traffic)
- [ ] `GET /capabilities` lists all 4 platforms.
- [ ] `GET /categories?url=<cmc index>` returns categories.
- [ ] A Top-5 extraction on at least one platform completes and exports a CSV.
- [ ] `GET /download/csv` and `GET /download/xlsx` return files.

## Operational readiness
- [ ] Logs accessible (platform dashboard or `docker logs`).
- [ ] Rollback path known (redeploy previous image/build).
- [ ] Team has access to [`RUNBOOK.md`](RUNBOOK.md).

> When every box is checked, proceed to [`POST_DEPLOY_VERIFICATION.md`](POST_DEPLOY_VERIFICATION.md).
