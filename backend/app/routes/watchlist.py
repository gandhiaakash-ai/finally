"""Watchlist REST endpoints."""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.db import watchlist
from app.db.connection import DEFAULT_USER_ID
from app.market import MarketDataSource, PriceCache

TICKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


class AddTickerRequest(BaseModel):
    ticker: str = Field(..., description="Ticker symbol")

    @field_validator("ticker")
    @classmethod
    def _normalize(cls, v: str) -> str:
        return v.strip().upper()


def _validate_ticker(ticker: str) -> None:
    if not TICKER_PATTERN.fullmatch(ticker):
        raise HTTPException(status_code=400, detail=f"Invalid ticker: {ticker!r}")


def create_watchlist_router(
    price_cache: PriceCache,
    get_source: callable,
) -> APIRouter:
    """Build the watchlist router.

    `get_source` is a callable returning the current MarketDataSource so the
    router resolves it lazily (lifespan starts the source after route setup).
    """
    router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])

    @router.get("")
    async def list_watchlist() -> dict:
        tickers = watchlist.list_tickers(user_id=DEFAULT_USER_ID)
        return {
            "tickers": [
                _ticker_payload(ticker, price_cache) for ticker in tickers
            ]
        }

    @router.post("")
    async def add_to_watchlist(payload: AddTickerRequest) -> dict:
        _validate_ticker(payload.ticker)
        inserted = watchlist.add_ticker(payload.ticker, user_id=DEFAULT_USER_ID)
        source = _require_source(get_source)
        if inserted:
            await source.add_ticker(payload.ticker)
        return {
            "ticker": payload.ticker,
            "added": inserted,
            "tickers": watchlist.list_tickers(user_id=DEFAULT_USER_ID),
        }

    @router.delete("/{ticker}")
    async def remove_from_watchlist(ticker: str) -> dict:
        ticker = ticker.strip().upper()
        _validate_ticker(ticker)
        removed = watchlist.remove_ticker(ticker, user_id=DEFAULT_USER_ID)
        if not removed:
            raise HTTPException(status_code=404, detail=f"Ticker not on watchlist: {ticker}")
        source = _require_source(get_source)
        await source.remove_ticker(ticker)
        return {
            "ticker": ticker,
            "removed": True,
            "tickers": watchlist.list_tickers(user_id=DEFAULT_USER_ID),
        }

    return router


def _ticker_payload(ticker: str, price_cache: PriceCache) -> dict:
    update = price_cache.get(ticker)
    return {
        "ticker": ticker,
        "price": update.to_dict() if update is not None else None,
    }


def _require_source(get_source: callable) -> MarketDataSource:
    source = get_source()
    if source is None:
        raise HTTPException(status_code=503, detail="Market data source not ready")
    return source
