"""Trade execution.

`execute_trade` is the single source of truth for buying and selling. Both the
manual REST trade endpoint and the LLM auto-execution path call it so the same
validation, accounting, and side-effects apply.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.db import positions as positions_db
from app.db import trades, users
from app.db.connection import DEFAULT_USER_ID
from app.db.trades import Trade
from app.market import PriceCache
from app.portfolio.snapshots import record_snapshot_now
from app.portfolio.valuation import PortfolioSummary, portfolio_summary

Side = Literal["buy", "sell"]


class TradeError(Exception):
    """Raised when a trade fails validation. Message is safe to surface to users."""


@dataclass(frozen=True)
class TradeResult:
    trade: Trade
    summary: PortfolioSummary

    def to_dict(self) -> dict:
        return {
            "trade": {
                "id": self.trade.id,
                "ticker": self.trade.ticker,
                "side": self.trade.side,
                "quantity": self.trade.quantity,
                "price": self.trade.price,
                "executed_at": self.trade.executed_at,
            },
            "portfolio": self.summary.to_dict(),
        }


def execute_trade(
    ticker: str,
    side: Side,
    quantity: float,
    price_cache: PriceCache,
    user_id: str = DEFAULT_USER_ID,
) -> TradeResult:
    """Validate and execute a market order at the current cached price.

    Raises TradeError on any validation failure. On success, the trade row is
    inserted, the position is upserted (with weighted-average cost on buys),
    cash is updated, and a portfolio snapshot is recorded.
    """
    ticker = ticker.strip().upper()
    if not ticker:
        raise TradeError("Ticker is required")
    if side not in ("buy", "sell"):
        raise TradeError(f"Invalid side: {side!r}")
    if quantity <= 0:
        raise TradeError("Quantity must be greater than zero")

    price = price_cache.get_price(ticker)
    if price is None:
        raise TradeError(f"No price available for {ticker}")

    cost = price * quantity
    cash = users.get_cash_balance(user_id=user_id)
    existing = positions_db.get_position(ticker, user_id=user_id)

    if side == "buy":
        if cost > cash:
            raise TradeError(
                f"Insufficient cash: need ${cost:,.2f}, have ${cash:,.2f}"
            )
        new_quantity, new_avg_cost = _apply_buy(existing, quantity, price)
        new_cash = cash - cost
    else:
        held = existing.quantity if existing else 0.0
        if quantity > held:
            raise TradeError(
                f"Insufficient shares: trying to sell {quantity}, hold {held}"
            )
        new_quantity, new_avg_cost = _apply_sell(existing, quantity)
        new_cash = cash + cost

    trade = trades.insert_trade(
        ticker=ticker, side=side, quantity=quantity, price=price, user_id=user_id
    )
    if new_quantity == 0:
        positions_db.delete_position(ticker, user_id=user_id)
    else:
        positions_db.upsert_position(
            ticker=ticker,
            quantity=new_quantity,
            avg_cost=new_avg_cost,
            user_id=user_id,
        )
    users.update_cash_balance(new_cash, user_id=user_id)

    summary = portfolio_summary(price_cache, user_id=user_id)
    record_snapshot_now(price_cache, user_id=user_id)
    return TradeResult(trade=trade, summary=summary)


def _apply_buy(
    existing: positions_db.Position | None, quantity: float, price: float
) -> tuple[float, float]:
    """Return new (quantity, avg_cost) after a buy, using a weighted average."""
    if existing is None or existing.quantity == 0:
        return quantity, price
    total_quantity = existing.quantity + quantity
    blended_cost = (
        existing.avg_cost * existing.quantity + price * quantity
    ) / total_quantity
    return total_quantity, blended_cost


def _apply_sell(
    existing: positions_db.Position | None, quantity: float
) -> tuple[float, float]:
    """Return new (quantity, avg_cost) after a sell. Avg cost is unchanged."""
    assert existing is not None  # already guarded by caller
    return existing.quantity - quantity, existing.avg_cost
