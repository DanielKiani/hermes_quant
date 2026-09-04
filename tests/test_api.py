from fastapi.testclient import TestClient
import requests

from src.backend import main


client = TestClient(main.app)


def test_health_contract() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "hermes-quant-api"


def test_market_failure_is_typed_unavailable(monkeypatch) -> None:
    def fail(*_args, **_kwargs):
        raise ValueError("provider offline")

    monkeypatch.setattr(main, "fetch_terminal_snapshot", fail)
    response = client.get("/api/v1/terminal/AAPL")
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["data_status"] == "unavailable"
    assert detail["retryable"] is True


def test_backtest_request_rejects_invalid_cost() -> None:
    response = client.post(
        "/api/v1/backtests",
        json={"ticker": "AAPL", "transaction_cost_bps": -1},
    )
    assert response.status_code == 422


def test_backtest_request_rejects_crossed_probability_thresholds() -> None:
    response = client.post(
        "/api/v1/backtests",
        json={"ticker": "AAPL", "short_threshold": 0.6, "long_threshold": 0.52},
    )
    assert response.status_code == 422


def test_crypto_research_profile_uses_continuous_calendar() -> None:
    response = client.get("/api/v1/research-profile/crypto")
    assert response.status_code == 200
    payload = response.json()
    assert payload["asset_class"] == "crypto"
    assert payload["annualization_factor"] == 365
    assert payload["regime_reference"] == "BTC-USD 200-day trend"


def test_research_profile_rejects_unknown_asset_class() -> None:
    response = client.get("/api/v1/research-profile/futures")
    assert response.status_code == 503
    assert "Unsupported asset class" in response.json()["detail"]["message"]


def test_portfolio_rejects_duplicate_tickers() -> None:
    response = client.post(
        "/api/v1/portfolio",
        json={
            "positions": [
                {"ticker": "aapl", "quantity": 1},
                {"ticker": "AAPL", "quantity": 2},
            ]
        },
    )
    assert response.status_code == 422


def test_analysis_fails_fast_when_ollama_is_unavailable(monkeypatch) -> None:
    def offline(*_args, **_kwargs):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(main.requests, "get", offline)
    response = client.post(
        "/api/v1/analysis",
        json={"ticker": "AAPL", "model": "XGBoost"},
    )
    assert response.status_code == 503
    assert "Ollama service is unavailable" in response.json()["detail"]["message"]


def test_upcoming_events_contract(monkeypatch) -> None:
    monkeypatch.setattr(
        main,
        "fetch_upcoming_events",
        lambda ticker: {
            "data_status": "available",
            "classification": "observed",
            "ticker": ticker,
            "events": [
                {
                    "date": "2026-09-08",
                    "title": "U.S. Treasury 13-Week Bill auction",
                    "kind": "treasury",
                    "source": "U.S. TreasuryDirect upcoming securities API",
                }
            ],
            "sources": [],
        },
    )
    response = client.get("/api/v1/events/AAPL")
    assert response.status_code == 200
    payload = response.json()
    assert payload["classification"] == "observed"
    assert payload["ticker"] == "AAPL"
    assert payload["events"][0]["kind"] == "treasury"
