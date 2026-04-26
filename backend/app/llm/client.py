"""LLM client: LiteLLM via OpenRouter to gpt-oss-120b on Cerebras.

When LLM_MOCK=true, returns deterministic responses for tests instead of
hitting OpenRouter. Both modes return a parsed LLMResponse.
"""

from __future__ import annotations

import os
import re
from typing import Any

from app.llm.schema import LLMResponse, TradeAction, WatchlistChange
from app.llm.system_prompt import SYSTEM_PROMPT

MODEL = "openrouter/openai/gpt-oss-120b"
PROVIDER_ROUTING = {"provider": {"order": ["cerebras"]}}
REASONING_EFFORT = "low"


class LLMError(RuntimeError):
    """Raised when the LLM call fails or its response cannot be parsed."""


def _is_mock_mode() -> bool:
    return os.getenv("LLM_MOCK", "").strip().lower() == "true"


class LLMClient:
    """LiteLLM wrapper with structured-output + LLM_MOCK support."""

    def __init__(self, *, mock: bool | None = None) -> None:
        self._mock = _is_mock_mode() if mock is None else mock

    @property
    def mock(self) -> bool:
        return self._mock

    def complete(
        self,
        user_message: str,
        *,
        portfolio_context: str = "",
        history: list[dict[str, str]] | None = None,
    ) -> LLMResponse:
        """Run one chat turn and return the parsed structured response.

        ``history`` is most-recent-last as ``[{role, content}]``; the
        orchestrator decides how much to include.
        """
        if self._mock:
            return _mock_response(user_message)
        return self._call_live(user_message, portfolio_context, history or [])

    def _call_live(
        self,
        user_message: str,
        portfolio_context: str,
        history: list[dict[str, str]],
    ) -> LLMResponse:
        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not api_key:
            raise LLMError("OPENROUTER_API_KEY is not set")

        messages = _build_messages(user_message, portfolio_context, history)

        from litellm import completion  # imported lazily so tests don't need it

        try:
            response = completion(
                model=MODEL,
                messages=messages,
                response_format=LLMResponse,
                reasoning_effort=REASONING_EFFORT,
                extra_body=PROVIDER_ROUTING,
                api_key=api_key,
            )
        except Exception as exc:  # network / provider / auth errors
            raise LLMError(f"LLM call failed: {exc}") from exc

        content = _extract_content(response)
        try:
            return LLMResponse.model_validate_json(content)
        except Exception as exc:
            raise LLMError(f"Could not parse LLM response as JSON: {exc}\nRaw: {content!r}") from exc


def _build_messages(
    user_message: str,
    portfolio_context: str,
    history: list[dict[str, str]],
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if portfolio_context:
        messages.append({"role": "system", "content": f"Current portfolio context:\n{portfolio_context}"})
    for turn in history:
        role = turn.get("role")
        content = turn.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})
    return messages


def _extract_content(response: Any) -> str:
    """Pull the JSON string out of the LiteLLM completion response."""
    try:
        return response.choices[0].message.content
    except (AttributeError, IndexError, KeyError) as exc:
        raise LLMError(f"Unexpected LLM response shape: {response!r}") from exc


# ---------------------------------------------------------------------------
# Mock mode
# ---------------------------------------------------------------------------

_TRADE_RE = re.compile(
    r"\b(buy|sell)\s+(\d+(?:\.\d+)?)\s+(?:shares?\s+of\s+)?([A-Za-z]{1,5})\b",
    re.IGNORECASE,
)
_WATCHLIST_ADD_RE = re.compile(r"\badd\s+([A-Za-z]{1,5})\s+to\s+(?:my\s+)?watchlist\b", re.IGNORECASE)
_WATCHLIST_REMOVE_RE = re.compile(
    r"\bremove\s+([A-Za-z]{1,5})\s+from\s+(?:my\s+)?watchlist\b", re.IGNORECASE
)
_GREETING_RE = re.compile(r"^\s*(hi|hello|hey|yo|hola)\b", re.IGNORECASE)
_PORTFOLIO_RE = re.compile(r"\b(portfolio|positions?|holdings?|how am i doing|my balance)\b", re.IGNORECASE)


def _mock_response(user_message: str) -> LLMResponse:
    """Deterministic responses for E2E tests covering common scenarios."""
    text = user_message.strip()

    trade_match = _TRADE_RE.search(text)
    if trade_match:
        side = trade_match.group(1).lower()
        qty = float(trade_match.group(2))
        ticker = trade_match.group(3).upper()
        return LLMResponse(
            message=f"Placing a market {side} for {qty:g} {ticker}.",
            trades=[TradeAction(ticker=ticker, side=side, quantity=qty)],
        )

    add_match = _WATCHLIST_ADD_RE.search(text)
    if add_match:
        ticker = add_match.group(1).upper()
        return LLMResponse(
            message=f"Added {ticker} to your watchlist.",
            watchlist_changes=[WatchlistChange(ticker=ticker, action="add")],
        )

    remove_match = _WATCHLIST_REMOVE_RE.search(text)
    if remove_match:
        ticker = remove_match.group(1).upper()
        return LLMResponse(
            message=f"Removed {ticker} from your watchlist.",
            watchlist_changes=[WatchlistChange(ticker=ticker, action="remove")],
        )

    if _PORTFOLIO_RE.search(text):
        return LLMResponse(
            message=(
                "Here is a summary of your portfolio: see the positions table and P&L "
                "chart for details. Let me know if you want to rebalance."
            ),
        )

    if _GREETING_RE.search(text):
        return LLMResponse(
            message="Hi, I'm FinAlly. Ask me about your portfolio or tell me to place a trade.",
        )

    return LLMResponse(
        message=(
            "I'm in mock mode and didn't recognise that request. Try 'what's my portfolio', "
            "'buy 10 shares of AAPL', or 'add NVDA to my watchlist'."
        ),
    )


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_default_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Return a process-wide LLMClient. Mode is decided once at first call."""
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client


def reset_llm_client() -> None:
    """Test helper: clear the cached client so env var changes take effect."""
    global _default_client
    _default_client = None


__all__ = [
    "LLMClient",
    "LLMError",
    "get_llm_client",
    "reset_llm_client",
    "MODEL",
    "PROVIDER_ROUTING",
]
