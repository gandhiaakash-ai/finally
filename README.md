# FinAlly

AI-powered trading workstation. Streams live market data, simulates a $10k portfolio, and embeds an LLM chat assistant that can analyse positions and execute trades.

Single Docker container, single port, SQLite for state. Bloomberg-style dark UI.

## Quick start

Set `OPENROUTER_API_KEY` in `.env` (copy from `.env.example`), then:

```bash
scripts/start_mac.sh        # macOS / Linux
scripts/start_windows.ps1   # Windows PowerShell
```

App is available at <http://localhost:8000>.

To stop:

```bash
scripts/stop_mac.sh         # macOS / Linux
scripts/stop_windows.ps1    # Windows PowerShell
```

The SQLite database persists in the `finally-data` Docker volume across restarts.

## Environment variables

| Variable | Required | Default | Notes |
|---|---|---|---|
| `OPENROUTER_API_KEY` | yes | — | Powers the AI chat assistant |
| `MASSIVE_API_KEY` | no | unset | If set, real Polygon-backed market data; otherwise built-in simulator |
| `LLM_MOCK` | no | `false` | `true` returns deterministic LLM responses (used by E2E) |

## Architecture

- `backend/` — FastAPI + uv. Owns market-data simulator, SSE streaming, REST API, LLM orchestration, SQLite.
- `frontend/` — Next.js + TypeScript + Tailwind. Built as a static export and served by FastAPI from `/`.
- `test/` — Playwright E2E suite + `docker-compose.test.yml`.
- `scripts/` — Idempotent start/stop wrappers around `docker run`.
- `planning/PLAN.md` — Full project specification.

## Running tests

```bash
# Backend unit/integration (300+ tests)
cd backend && uv run --extra dev pytest

# Frontend unit (Vitest)
cd frontend && npm test

# Full E2E (builds image, runs Playwright in compose)
docker compose -f test/docker-compose.test.yml up --abort-on-container-exit --exit-code-from runner --build
```
