"""Integration tests for portfolio and watchlist REST endpoints."""

from __future__ import annotations


def test_health_returns_ok(app_client):
    client, _, _ = app_client
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_portfolio_initial_shape(app_client):
    client, _, _ = app_client
    res = client.get("/api/portfolio")
    assert res.status_code == 200
    body = res.json()
    assert body == {
        "cash_balance": 10_000.0,
        "positions": [],
        "positions_value": 0.0,
        "total_value": 10_000.0,
        "total_cost_basis": 0.0,
        "total_unrealized_pl": 0.0,
    }


def test_trade_post_buys_then_returns_updated_summary(app_client):
    client, _, _ = app_client
    res = client.post(
        "/api/portfolio/trade",
        json={"ticker": "aapl", "side": "buy", "quantity": 5},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["trade"]["ticker"] == "AAPL"
    assert body["trade"]["price"] == 200.0
    assert body["portfolio"]["cash_balance"] == 9_000.0
    pos = body["portfolio"]["positions"]
    assert len(pos) == 1 and pos[0]["ticker"] == "AAPL"


def test_trade_buy_insufficient_cash_returns_400(app_client):
    client, _, _ = app_client
    res = client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "side": "buy", "quantity": 10_000},
    )
    assert res.status_code == 400
    assert "Insufficient cash" in res.json()["detail"]


def test_trade_sell_without_position_returns_400(app_client):
    client, _, _ = app_client
    res = client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "side": "sell", "quantity": 1},
    )
    assert res.status_code == 400
    assert "Insufficient shares" in res.json()["detail"]


def test_trade_zero_quantity_returns_422(app_client):
    """Pydantic validation rejects quantity <= 0 before reaching execute_trade."""
    client, _, _ = app_client
    res = client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "side": "buy", "quantity": 0},
    )
    assert res.status_code == 422


def test_history_starts_empty_then_grows_after_trade(app_client):
    client, _, _ = app_client
    assert client.get("/api/portfolio/history").json() == {"snapshots": []}

    client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "side": "buy", "quantity": 1},
    )

    snapshots = client.get("/api/portfolio/history").json()["snapshots"]
    assert len(snapshots) == 1
    assert snapshots[0]["total_value"] == 10_000.0  # cost-basis of single buy at fill price


def test_watchlist_get_returns_seeded_tickers_with_prices(app_client):
    client, _, _ = app_client
    body = client.get("/api/watchlist").json()
    tickers = {t["ticker"] for t in body["tickers"]}
    assert tickers == {
        "AAPL", "GOOGL", "MSFT", "AMZN", "TSLA",
        "NVDA", "META", "JPM", "V", "NFLX",
    }
    assert all(t["price"] is not None for t in body["tickers"])


def test_watchlist_add_calls_market_source(app_client):
    client, _, stub = app_client
    res = client.post("/api/watchlist", json={"ticker": "PYPL"})
    assert res.status_code == 200
    body = res.json()
    assert body["ticker"] == "PYPL"
    assert body["added"] is True
    assert "PYPL" in body["tickers"]
    assert stub.added == ["PYPL"]


def test_watchlist_add_existing_is_idempotent_and_skips_source(app_client):
    client, _, stub = app_client
    res = client.post("/api/watchlist", json={"ticker": "AAPL"})
    assert res.status_code == 200
    body = res.json()
    assert body["added"] is False
    assert stub.added == []  # no source call when row already exists


def test_watchlist_add_invalid_ticker_returns_400(app_client):
    client, _, _ = app_client
    res = client.post("/api/watchlist", json={"ticker": "12345"})
    assert res.status_code == 400


def test_watchlist_delete_calls_market_source(app_client):
    client, _, stub = app_client
    res = client.delete("/api/watchlist/AAPL")
    assert res.status_code == 200
    body = res.json()
    assert body["removed"] is True
    assert "AAPL" not in body["tickers"]
    assert stub.removed == ["AAPL"]


def test_watchlist_delete_unknown_ticker_returns_404(app_client):
    client, _, _ = app_client
    res = client.delete("/api/watchlist/PYPL")
    assert res.status_code == 404
