"""Portfolio REST endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from app.db import snapshots
from app.db.connection import DEFAULT_USER_ID
from app.market import PriceCache
from app.portfolio import TradeError, execute_trade, portfolio_summary


class TradeRequest(BaseModel):
    ticker: str = Field(..., description="Ticker symbol")
    side: Literal["buy", "sell"]
    quantity: float = Field(..., gt=0)

    @field_validator("ticker")
    @classmethod
    def _normalize(cls, v: str) -> str:
        return v.strip().upper()


def create_portfolio_router(price_cache: PriceCache) -> APIRouter:
    router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

    @router.get("")
    async def get_portfolio() -> dict:
        return portfolio_summary(price_cache, user_id=DEFAULT_USER_ID).to_dict()

    @router.post("/trade")
    async def post_trade(payload: TradeRequest) -> dict:
        try:
            result = execute_trade(
                ticker=payload.ticker,
                side=payload.side,
                quantity=payload.quantity,
                price_cache=price_cache,
                user_id=DEFAULT_USER_ID,
            )
        except TradeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return result.to_dict()

    @router.get("/history")
    async def get_history(
        since: str | None = Query(None, description="ISO timestamp lower bound"),
        limit: int | None = Query(None, ge=1, le=10_000),
    ) -> dict:
        rows = snapshots.list_snapshots(
            user_id=DEFAULT_USER_ID, since=since, limit=limit
        )
        return {
            "snapshots": [
                {
                    "id": s.id,
                    "total_value": s.total_value,
                    "recorded_at": s.recorded_at,
                }
                for s in rows
            ]
        }

    return router
