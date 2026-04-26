"""Chat orchestration: build context, call LLM, execute actions, persist.

End-to-end flow per PLAN.md §9:

1. Build portfolio context (cash, positions w/ P&L, watchlist).
2. Load recent chat history.
3. Call the LLM client with context + history + the new user message.
4. For each trade in the structured response, call ``app.portfolio.execute_trade``.
   Per-trade failures are captured, never raised.
5. Apply each watchlist change (DB + market data source).
6. Persist the user message + assistant message (with executed-actions JSON).
7. Return a ``ChatResult`` for the API layer to JSON-serialize.

Action execution is done through injectable callables so tests can swap them
out without spinning up a real market data source.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Literal

from pydantic import BaseModel

from app.db import chat as chat_db
from app.db import watchlist as watchlist_db
from app.db.connection import DEFAULT_USER_ID
from app.llm.client import LLMClient, LLMError, get_llm_client
from app.llm.context import build_snapshot, load_history, render_snapshot
from app.llm.schema import TradeAction, WatchlistChange
from app.market import MarketDataSource, PriceCache
from app.portfolio import TradeError, execute_trade

HISTORY_LIMIT = 10


class ExecutedTrade(BaseModel):
    ticker: str
    side: Literal["buy", "sell"]
    quantity: float
    price: float | None = None
    status: Literal["filled", "failed"]
    error: str | None = None


class AppliedWatchlistChange(BaseModel):
    ticker: str
    action: Literal["add", "remove"]
    status: Literal["applied", "failed"]
    error: str | None = None


class ChatResult(BaseModel):
    message: str
    trades: list[ExecutedTrade] = []
    watchlist_changes: list[AppliedWatchlistChange] = []


TradeExecutor = Callable[[TradeAction, str], Awaitable[ExecutedTrade]]
WatchlistApplier = Callable[[WatchlistChange, str], Awaitable[AppliedWatchlistChange]]


async def handle_chat_message(
    user_message: str,
    *,
    user_id: str = DEFAULT_USER_ID,
    price_cache: PriceCache | None = None,
    market_source: MarketDataSource | None = None,
    llm_client: LLMClient | None = None,
    trade_executor: TradeExecutor | None = None,
    watchlist_applier: WatchlistApplier | None = None,
) -> ChatResult:
    """Run one chat turn and return the structured result.

    Defaults wire up the production dependencies; tests pass overrides.
    """
    cache = price_cache if price_cache is not None else _resolve_price_cache()
    source = market_source if market_source is not None else _resolve_market_source()
    client = llm_client or get_llm_client()
    do_trade = trade_executor or _make_trade_executor(cache)
    do_watchlist = watchlist_applier or _make_watchlist_applier(source)

    snapshot = build_snapshot(cache, user_id=user_id)
    context_text = render_snapshot(snapshot)
    history = load_history(limit=HISTORY_LIMIT, user_id=user_id)

    chat_db.insert_message(role="user", content=user_message, user_id=user_id)

    try:
        llm_response = await asyncio.to_thread(
            client.complete,
            user_message,
            portfolio_context=context_text,
            history=history,
        )
    except LLMError as exc:
        message = f"Sorry, the AI assistant is unavailable right now ({exc})."
        chat_db.insert_message(role="assistant", content=message, user_id=user_id)
        return ChatResult(message=message)

    executed_trades = [await do_trade(t, user_id) for t in llm_response.trades]
    applied_watchlist = [await do_watchlist(c, user_id) for c in llm_response.watchlist_changes]

    actions_payload = {
        "trades": [t.model_dump() for t in executed_trades],
        "watchlist_changes": [w.model_dump() for w in applied_watchlist],
    }
    chat_db.insert_message(
        role="assistant",
        content=llm_response.message,
        actions=actions_payload,
        user_id=user_id,
    )

    return ChatResult(
        message=llm_response.message,
        trades=executed_trades,
        watchlist_changes=applied_watchlist,
    )


def _make_trade_executor(price_cache: PriceCache) -> TradeExecutor:
    async def _do(action: TradeAction, user_id: str) -> ExecutedTrade:
        try:
            result = execute_trade(
                ticker=action.ticker,
                side=action.side,
                quantity=action.quantity,
                price_cache=price_cache,
                user_id=user_id,
            )
        except TradeError as exc:
            return ExecutedTrade(
                ticker=action.ticker,
                side=action.side,
                quantity=action.quantity,
                status="failed",
                error=str(exc),
            )
        return ExecutedTrade(
            ticker=action.ticker,
            side=action.side,
            quantity=action.quantity,
            price=result.trade.price,
            status="filled",
        )

    return _do


def _make_watchlist_applier(source: MarketDataSource | None) -> WatchlistApplier:
    async def _do(change: WatchlistChange, user_id: str) -> AppliedWatchlistChange:
        try:
            if change.action == "add":
                inserted = watchlist_db.add_ticker(change.ticker, user_id=user_id)
                if inserted and source is not None:
                    await source.add_ticker(change.ticker)
            else:
                removed = watchlist_db.remove_ticker(change.ticker, user_id=user_id)
                if not removed:
                    return AppliedWatchlistChange(
                        ticker=change.ticker,
                        action=change.action,
                        status="failed",
                        error=f"Ticker not on watchlist: {change.ticker}",
                    )
                if source is not None:
                    await source.remove_ticker(change.ticker)
        except Exception as exc:
            return AppliedWatchlistChange(
                ticker=change.ticker,
                action=change.action,
                status="failed",
                error=str(exc),
            )
        return AppliedWatchlistChange(
            ticker=change.ticker, action=change.action, status="applied"
        )

    return _do


def _resolve_price_cache() -> PriceCache:
    from app.state import state
    return state.price_cache


def _resolve_market_source() -> MarketDataSource | None:
    from app.state import state
    return state.market_source
