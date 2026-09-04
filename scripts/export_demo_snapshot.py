"""Capture a compact, explicitly frozen API snapshot for the GitHub Pages demo."""

from __future__ import annotations

import argparse
import json
import math
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "frontend" / "demo" / "snapshot.json"
PORTFOLIO = [
    {"ticker": "AAPL", "quantity": 12},
    {"ticker": "MSFT", "quantity": 8},
    {"ticker": "SPY", "quantity": 10},
    {"ticker": "NVDA", "quantity": 6},
]


def request_json(base_url: str, path: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST" if body is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.load(response)


def sample_series(points: list[dict], limit: int = 220) -> list[dict]:
    if len(points) <= limit:
        return points
    stride = math.ceil((len(points) - 1) / (limit - 1))
    sampled = points[::stride]
    if sampled[-1] != points[-1]:
        sampled.append(points[-1])
    return sampled


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    overviews = {
        asset_class: request_json(args.base_url, f"/api/v1/market-overview?asset_class={asset_class}")
        for asset_class in ("equity", "crypto")
    }
    profiles = {
        asset_class: request_json(args.base_url, f"/api/v1/research-profile/{asset_class}")
        for asset_class in ("equity", "crypto")
    }
    tickers = {
        item["ticker"]
        for overview in overviews.values()
        for item in overview.get("tape", [])
    }
    tickers.update({"AAPL", "BTC-USD"})

    terminals: dict[str, dict] = {}
    for ticker in sorted(tickers):
        encoded = urllib.parse.quote(ticker, safe="")
        try:
            terminals[ticker] = request_json(args.base_url, f"/api/v1/terminal/{encoded}?period=6mo")
        except Exception as error:  # A partial snapshot remains honest and usable.
            print(f"Skipping terminal snapshot for {ticker}: {error}")

    news = {}
    events = {}
    for ticker in ("AAPL", "BTC-USD", "^GSPC"):
        encoded = urllib.parse.quote(ticker, safe="")
        try:
            news[ticker] = request_json(args.base_url, f"/api/v1/news/{encoded}?limit=12")
        except Exception as error:
            print(f"Skipping news snapshot for {ticker}: {error}")
    for ticker in ("AAPL", "BTC-USD", "SPY"):
        encoded = urllib.parse.quote(ticker, safe="")
        try:
            events[ticker] = request_json(args.base_url, f"/api/v1/events/{encoded}")
        except Exception as error:
            print(f"Skipping event snapshot for {ticker}: {error}")

    portfolio = request_json(
        args.base_url,
        "/api/v1/portfolio",
        {"positions": PORTFOLIO, "confidence": 0.95},
    )
    backtest = request_json(
        args.base_url,
        "/api/v1/backtests",
        {
            "ticker": "AAPL",
            "asset_class": "equity",
            "engine": "sma",
            "short_window": 20,
            "long_window": 50,
            "train_window": 750,
            "test_window": 63,
            "validation_fraction": 0.2,
            "target_horizon": 5,
            "long_threshold": 0.54,
            "short_threshold": 0.46,
            "position_mode": "long_cash",
            "transaction_cost_bps": 5,
            "slippage_bps": 2,
            "risk_free_rate": 0,
            "lookback_years": 3,
            "use_regime_filter": False,
            "n_trials": 1,
        },
    )
    backtest["series"] = sample_series(backtest.get("series", []))

    snapshot = {
        "demo": {
            "mode": "frozen",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "notice": "Frozen provider snapshot for interface demonstration only.",
        },
        "market_overview": overviews,
        "research_profile": profiles,
        "terminal": terminals,
        "news": news,
        "events": events,
        "portfolio": portfolio,
        "backtest": backtest,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {args.output} ({args.output.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
