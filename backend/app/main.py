"""FastAPI application entry point for FinAlly.

The lifespan handler:
  1. Loads .env from the project root.
  2. Lazily initialises the SQLite database (idempotent).
  3. Starts the market data source against the current watchlist.
  4. Starts the portfolio snapshot background task (placeholder until task #6).

Static frontend assets are served from `backend/static/` at the root path.
The Next.js export is copied here by the Dockerfile; in dev the directory may
not exist yet, in which case static mounting is skipped.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles

from app.db import init_db, watchlist
from app.db.schema import DEFAULT_TICKERS
from app.market import create_market_data_source, create_stream_router
from app.routes.chat import create_chat_router
from app.routes.portfolio import create_portfolio_router
from app.routes.watchlist import create_watchlist_router
from app.state import state

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def _load_initial_tickers() -> list[str]:
    """Return the watchlist tickers to start the market source with."""
    tickers = watchlist.list_tickers()
    return tickers if tickers else list(DEFAULT_TICKERS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv(PROJECT_ROOT / ".env")
    logging.basicConfig(level=logging.INFO)

    init_db()
    logger.info("Database initialised")

    tickers = _load_initial_tickers()
    state.market_source = create_market_data_source(state.price_cache)
    await state.market_source.start(tickers)
    logger.info("Market data source started with %d tickers", len(tickers))

    state.snapshot_task = await _start_snapshot_task()

    try:
        yield
    finally:
        if state.snapshot_task is not None:
            state.snapshot_task.cancel()
            try:
                await state.snapshot_task
            except BaseException:
                pass
        if state.market_source is not None:
            await state.market_source.stop()
        logger.info("Shutdown complete")


async def _start_snapshot_task():
    """Start the portfolio snapshot background task if available.

    Returns None until task #6 ships its `start_snapshot_loop()` entry point.
    """
    try:
        from app.portfolio.snapshots import start_snapshot_loop  # type: ignore[import]

        return await start_snapshot_loop()
    except ImportError:
        return None


def create_app() -> FastAPI:
    app = FastAPI(title="FinAlly", lifespan=lifespan)

    api = APIRouter(prefix="/api", tags=["system"])

    @api.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(api)
    app.include_router(create_stream_router(state.price_cache))
    app.include_router(create_portfolio_router(state.price_cache))
    app.include_router(
        create_watchlist_router(state.price_cache, lambda: state.market_source)
    )
    app.include_router(create_chat_router())

    _mount_static(app)
    return app


def _mount_static(app: FastAPI) -> None:
    """Serve the Next.js static export at the root path.

    Mounted last so /api/* routes take precedence. `html=True` makes
    StaticFiles serve `index.html` for directory requests, supporting the
    SPA-style export Next.js produces.
    """
    if not STATIC_DIR.is_dir():
        logger.warning("Static directory %s not found; skipping mount", STATIC_DIR)
        return
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


app = create_app()
