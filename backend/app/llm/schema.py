"""Pydantic models for LLM structured output.

The LLM is asked to respond in JSON conforming to ``LLMResponse``. Trades and
watchlist changes are auto-executed by the chat orchestrator after validation.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class TradeAction(BaseModel):
    """A single trade the LLM wants the system to execute on the user's behalf."""

    ticker: str = Field(..., description="Ticker symbol, e.g. AAPL")
    side: Literal["buy", "sell"]
    quantity: float = Field(..., gt=0, description="Number of shares (fractional allowed)")

    @field_validator("ticker")
    @classmethod
    def _normalize_ticker(cls, v: str) -> str:
        return v.strip().upper()


class WatchlistChange(BaseModel):
    """An add or remove operation on the user's watchlist."""

    ticker: str = Field(..., description="Ticker symbol, e.g. AAPL")
    action: Literal["add", "remove"]

    @field_validator("ticker")
    @classmethod
    def _normalize_ticker(cls, v: str) -> str:
        return v.strip().upper()


class LLMResponse(BaseModel):
    """Top-level structured response returned by the LLM for every chat turn."""

    message: str = Field(..., description="Conversational response shown to the user")
    trades: list[TradeAction] = Field(default_factory=list)
    watchlist_changes: list[WatchlistChange] = Field(default_factory=list)
