"""Build the portfolio-context block injected into each LLM turn.

The block is a compact, human-readable text snapshot the model can reason
about without parsing JSON: cash, positions w/ unrealized P&L, watchlist
prices, and the total portfolio value.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.db import chat as chat_db
from app.db import positions as positions_db
from app.db import users as users_db
from app.db import watchlist as watchlist_db
from app.db.connection import DEFAULT_USER_ID
from app.market import PriceCache


@dataclass(frozen=True)
class PortfolioSnapshot:
    cash: float
    total_value: float
    positions: list["PositionLine"]
    watchlist: list["WatchlistLine"]


@dataclass(frozen=True)
class PositionLine:
    ticker: str
    quantity: float
    avg_cost: float
    price: float | None
    market_value: float
    unrealized_pl: float
    unrealized_pl_pct: float | None


@dataclass(frozen=True)
class WatchlistLine:
    ticker: str
    price: float | None


def build_snapshot(price_cache: PriceCache, user_id: str = DEFAULT_USER_ID) -> PortfolioSnapshot:
    """Read DB + price cache and assemble a snapshot of the user's account."""
    cash = users_db.get_cash_balance(user_id)
    rows = positions_db.list_positions(user_id)
    watch = watchlist_db.list_tickers(user_id)

    position_lines: list[PositionLine] = []
    positions_value = 0.0
    for row in rows:
        price = price_cache.get_price(row.ticker)
        if price is not None:
            mv = row.quantity * price
            cost = row.quantity * row.avg_cost
            pl = mv - cost
            pl_pct = (pl / cost * 100.0) if cost else None
        else:
            mv = 0.0
            pl = 0.0
            pl_pct = None
        positions_value += mv
        position_lines.append(
            PositionLine(
                ticker=row.ticker,
                quantity=row.quantity,
                avg_cost=row.avg_cost,
                price=price,
                market_value=mv,
                unrealized_pl=pl,
                unrealized_pl_pct=pl_pct,
            )
        )

    watchlist_lines = [WatchlistLine(ticker=t, price=price_cache.get_price(t)) for t in watch]

    return PortfolioSnapshot(
        cash=cash,
        total_value=cash + positions_value,
        positions=position_lines,
        watchlist=watchlist_lines,
    )


def render_snapshot(snapshot: PortfolioSnapshot) -> str:
    """Format a PortfolioSnapshot as a compact text block for the LLM."""
    lines: list[str] = []
    lines.append(f"Cash: ${snapshot.cash:,.2f}")
    lines.append(f"Total portfolio value: ${snapshot.total_value:,.2f}")

    if snapshot.positions:
        lines.append("")
        lines.append("Positions:")
        for p in snapshot.positions:
            price_s = f"${p.price:,.2f}" if p.price is not None else "n/a"
            pct_s = f"{p.unrealized_pl_pct:+.2f}%" if p.unrealized_pl_pct is not None else "n/a"
            lines.append(
                f"  {p.ticker}: qty={p.quantity:g} @ avg ${p.avg_cost:,.2f}, "
                f"price={price_s}, mv=${p.market_value:,.2f}, "
                f"P&L=${p.unrealized_pl:+,.2f} ({pct_s})"
            )
    else:
        lines.append("")
        lines.append("Positions: none")

    if snapshot.watchlist:
        lines.append("")
        lines.append("Watchlist:")
        for w in snapshot.watchlist:
            price_s = f"${w.price:,.2f}" if w.price is not None else "n/a"
            lines.append(f"  {w.ticker}: {price_s}")

    return "\n".join(lines)


def load_history(
    limit: int = 10,
    user_id: str = DEFAULT_USER_ID,
) -> list[dict[str, str]]:
    """Recent chat history as ``[{role, content}]`` ordered oldest-first."""
    msgs = chat_db.list_recent_messages(limit=limit, user_id=user_id)
    return [{"role": m.role, "content": m.content} for m in msgs]
