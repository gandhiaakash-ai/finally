"""Portfolio valuation — pure functions over positions and current prices."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from app.db import positions as positions_db
from app.db import users
from app.market import PriceCache


@dataclass(frozen=True)
class PositionView:
    ticker: str
    quantity: float
    avg_cost: float
    current_price: float | None
    market_value: float
    unrealized_pl: float
    unrealized_pl_percent: float


@dataclass(frozen=True)
class PortfolioSummary:
    cash_balance: float
    positions: list[PositionView]
    positions_value: float
    total_value: float
    total_cost_basis: float
    total_unrealized_pl: float

    def to_dict(self) -> dict:
        return {
            "cash_balance": self.cash_balance,
            "positions": [asdict(p) for p in self.positions],
            "positions_value": self.positions_value,
            "total_value": self.total_value,
            "total_cost_basis": self.total_cost_basis,
            "total_unrealized_pl": self.total_unrealized_pl,
        }


def _value_position(
    position: positions_db.Position, current_price: float | None
) -> PositionView:
    if current_price is None:
        market_value = position.quantity * position.avg_cost
        unrealized_pl = 0.0
        unrealized_pl_percent = 0.0
    else:
        market_value = position.quantity * current_price
        cost_basis = position.quantity * position.avg_cost
        unrealized_pl = market_value - cost_basis
        unrealized_pl_percent = (
            (current_price - position.avg_cost) / position.avg_cost * 100.0
            if position.avg_cost
            else 0.0
        )
    return PositionView(
        ticker=position.ticker,
        quantity=position.quantity,
        avg_cost=position.avg_cost,
        current_price=current_price,
        market_value=market_value,
        unrealized_pl=unrealized_pl,
        unrealized_pl_percent=unrealized_pl_percent,
    )


def portfolio_summary(price_cache: PriceCache, user_id: str = "default") -> PortfolioSummary:
    """Build a full portfolio summary from DB state plus the live price cache."""
    cash = users.get_cash_balance(user_id=user_id)
    rows = positions_db.list_positions(user_id=user_id)
    views = [_value_position(p, price_cache.get_price(p.ticker)) for p in rows]
    positions_value = sum(v.market_value for v in views)
    total_cost_basis = sum(p.quantity * p.avg_cost for p in rows)
    total_unrealized_pl = sum(v.unrealized_pl for v in views)
    return PortfolioSummary(
        cash_balance=cash,
        positions=views,
        positions_value=positions_value,
        total_value=cash + positions_value,
        total_cost_basis=total_cost_basis,
        total_unrealized_pl=total_unrealized_pl,
    )
