# syntax=docker/dockerfile:1.7

# ---------- Stage 1: build the Next.js static export ----------
FROM node:20-slim AS frontend-builder

WORKDIR /build

# Install deps first (cached unless package files change).
# Use `npm install` rather than `npm ci`: the lockfile is generated on the
# developer's host and may resolve different optional binary deps (e.g. sharp)
# than the Linux build environment. `npm install` reconciles those gracefully.
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund

# Copy the rest of the frontend source and build the static export
COPY frontend/ ./
RUN npm run build

# At this point, /build/out/ contains the static export.

# ---------- Stage 2: Python runtime (FastAPI) ----------
FROM python:3.12-slim AS runtime

# uv is the project's package manager (per CLAUDE.md). Use the official static binary.
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /usr/local/bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    FINALLY_DB_PATH=/app/db/finally.db

WORKDIR /app

# Install Python deps with uv (cached on lockfile + manifest)
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Copy the backend application code and finalize the project install
COPY backend/ ./
RUN uv sync --frozen --no-dev

# Copy the built frontend into the location FastAPI serves static files from.
# Backend serves /app/static as the static-file root (path coordinated with backend-engineer).
COPY --from=frontend-builder /build/out /app/static

# Volume mount target for the SQLite database
RUN mkdir -p /app/db
VOLUME ["/app/db"]

EXPOSE 8000

# Healthcheck hits the API health endpoint; relies on python stdlib so no extra deps required.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
