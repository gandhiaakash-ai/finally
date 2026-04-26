"""LLM integration package: structured output schema, client, and chat orchestration."""

from app.llm.client import LLMClient, LLMError, get_llm_client
from app.llm.orchestrator import (
    AppliedWatchlistChange,
    ChatResult,
    ExecutedTrade,
    handle_chat_message,
)
from app.llm.schema import LLMResponse, TradeAction, WatchlistChange

__all__ = [
    "AppliedWatchlistChange",
    "ChatResult",
    "ExecutedTrade",
    "LLMClient",
    "LLMError",
    "LLMResponse",
    "TradeAction",
    "WatchlistChange",
    "get_llm_client",
    "handle_chat_message",
]
