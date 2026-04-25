"""Tests for the SSE streaming router and event generator.

`_generate_events` is exercised directly with a fake Request because
`httpx.ASGITransport` buffers complete responses and does not stream
SSE events in a way that's testable end-to-end.
"""

import asyncio
import json

import pytest
from fastapi import FastAPI

from app.market.cache import PriceCache
from app.market.stream import _generate_events, create_stream_router


class FakeRequest:
    """Minimal stand-in for fastapi.Request.

    The generator only touches `client` (for logging) and
    `is_disconnected()` (for the exit condition), so we don't need a
    real ASGI scope.
    """

    def __init__(self) -> None:
        self.client = None
        self._disconnected = False

    async def is_disconnected(self) -> bool:
        return self._disconnected

    def disconnect(self) -> None:
        self._disconnected = True


async def _next(gen, timeout: float = 1.0) -> str:
    """Pull one event from the generator with a hard timeout."""
    return await asyncio.wait_for(gen.__anext__(), timeout=timeout)


async def _expect_stop(gen, timeout: float = 1.0) -> None:
    """Assert the generator has stopped (or stops within `timeout`)."""
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(gen.__anext__(), timeout=timeout)


@pytest.mark.asyncio
class TestGenerateEvents:
    """Direct tests of the SSE async generator."""

    async def test_emits_retry_directive_first(self):
        cache = PriceCache()
        request = FakeRequest()
        request.disconnect()  # exit on the first loop iteration

        gen = _generate_events(cache, request, interval=0.01)
        first = await _next(gen)
        await _expect_stop(gen)

        assert first == "retry: 1000\n\n"

    async def test_emits_data_event_when_cache_has_data(self):
        cache = PriceCache()
        cache.update("AAPL", 190.50)
        cache.update("GOOGL", 175.00)
        request = FakeRequest()

        gen = _generate_events(cache, request, interval=0.01)
        retry = await _next(gen)
        data = await _next(gen)
        request.disconnect()
        await _expect_stop(gen)

        assert retry == "retry: 1000\n\n"
        assert data.startswith("data: ")
        payload = json.loads(data[len("data: "):].strip())
        assert set(payload.keys()) == {"AAPL", "GOOGL"}
        assert payload["AAPL"]["price"] == 190.50
        assert payload["AAPL"]["direction"] == "flat"

    async def test_skips_emit_when_version_unchanged(self):
        """Idle ticks (no cache mutation) must not produce data events."""
        cache = PriceCache()
        cache.update("AAPL", 190.50)
        request = FakeRequest()

        gen = _generate_events(cache, request, interval=0.005)
        retry = await _next(gen)
        data1 = await _next(gen)

        # No further events expected without a cache change. wait_for
        # cancels the gen on timeout; the gen catches CancelledError and
        # exits, so we may see either TimeoutError or StopAsyncIteration.
        # Either outcome confirms no data was yielded during idle ticks.
        with pytest.raises((asyncio.TimeoutError, StopAsyncIteration)):
            await asyncio.wait_for(gen.__anext__(), timeout=0.05)

        assert retry == "retry: 1000\n\n"
        assert data1.startswith("data: ")

    async def test_emits_new_event_when_cache_updates(self):
        cache = PriceCache()
        cache.update("AAPL", 190.00)
        request = FakeRequest()

        gen = _generate_events(cache, request, interval=0.005)
        await _next(gen)               # retry
        first = await _next(gen)       # initial data

        cache.update("AAPL", 191.00)
        second = await _next(gen)      # data with the new price

        request.disconnect()
        await _expect_stop(gen)

        first_payload = json.loads(first[len("data: "):].strip())
        second_payload = json.loads(second[len("data: "):].strip())
        assert first_payload["AAPL"]["price"] == 190.00
        assert second_payload["AAPL"]["price"] == 191.00
        assert second_payload["AAPL"]["previous_price"] == 190.00
        assert second_payload["AAPL"]["direction"] == "up"

    async def test_breaks_on_disconnect_before_first_iteration(self):
        cache = PriceCache()
        cache.update("AAPL", 190.50)
        request = FakeRequest()
        request.disconnect()  # disconnect before the loop runs

        gen = _generate_events(cache, request, interval=0.01)
        retry = await _next(gen)
        await _expect_stop(gen)

        # Only the retry directive is emitted; no data event.
        assert retry == "retry: 1000\n\n"


class TestCreateStreamRouter:
    """Tests for the router factory itself."""

    def test_returns_independent_routers(self):
        """Two factory calls must produce independent router instances.

        Regression test for the previous module-level router bug, where
        repeated calls registered the same path on a shared router and
        the inner closure captured the wrong cache.
        """
        cache_a = PriceCache()
        cache_b = PriceCache()

        router_a = create_stream_router(cache_a)
        router_b = create_stream_router(cache_b)

        assert router_a is not router_b

        a_paths = [r.path for r in router_a.routes if hasattr(r, "path")]
        b_paths = [r.path for r in router_b.routes if hasattr(r, "path")]
        assert a_paths == ["/api/stream/prices"]
        assert b_paths == ["/api/stream/prices"]

    def test_router_mounts_on_fastapi_app(self):
        cache = PriceCache()
        app = FastAPI()
        app.include_router(create_stream_router(cache))

        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/api/stream/prices" in paths
