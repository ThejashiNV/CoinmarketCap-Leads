# Backend image for Render. Uses a Debian-based Python so Playwright can
# install Chromium + its system libraries at build time (the slim base alone
# lacks them, which is the usual cause of "browser launch failed" on PaaS).
FROM python:3.12-slim

WORKDIR /app

# Python deps first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Chromium + OS dependencies. `--with-deps` runs apt as root (fine in a build)
# and pulls the exact browser build matching the installed playwright version.
RUN playwright install --with-deps chromium

# App source (frontend and heavy dirs are excluded via .dockerignore).
COPY . .

# Render injects $PORT; default to 8000 for local `docker run`.
# IMPORTANT: single uvicorn worker — run state/logs are held in-process.
ENV PORT=8000
CMD ["sh", "-c", "uvicorn backend_api:app --host 0.0.0.0 --port ${PORT}"]
