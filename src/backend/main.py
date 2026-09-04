from __future__ import annotations

import os
from datetime import datetime, timezone

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from src.backend.models import AnalysisRequest, BacktestRequest, PortfolioRequest
from src.backend.services import (
    calculate_portfolio,
    fetch_market_overview,
    fetch_news,
    fetch_options_snapshot,
    fetch_research_profile,
    fetch_terminal_snapshot,
    fetch_upcoming_events,
    run_sma_backtest,
)


app = FastAPI(
    title="Hermes Quant Research API",
    version="2.0.0",
    description="Observed market data and explicitly labeled quantitative research outputs.",
)

origins = [
    origin.strip()
    for origin in os.getenv(
        "HERMES_ALLOWED_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080"
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def unavailable(error: Exception) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "data_status": "unavailable",
            "message": str(error),
            "retryable": True,
        },
    )


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "hermes-quant-api",
        "version": app.version,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/terminal/{ticker}")
async def terminal(ticker: str, period: str = Query(default="6mo")) -> dict:
    try:
        return await run_in_threadpool(fetch_terminal_snapshot, ticker, period)
    except Exception as error:
        raise unavailable(error) from error


@app.get("/api/v1/market-overview")
async def market_overview(asset_class: str = Query(default="equity", pattern="^(equity|crypto)$")) -> dict:
    try:
        return await run_in_threadpool(fetch_market_overview, asset_class)
    except Exception as error:
        raise unavailable(error) from error


@app.get("/api/v1/research-profile/{asset_class}")
async def research_profile(asset_class: str) -> dict:
    try:
        return await run_in_threadpool(fetch_research_profile, asset_class)
    except Exception as error:
        raise unavailable(error) from error


@app.get("/api/v1/options/{ticker}")
async def options(ticker: str) -> dict:
    try:
        return await run_in_threadpool(fetch_options_snapshot, ticker)
    except Exception as error:
        raise unavailable(error) from error


@app.get("/api/v1/news/{ticker}")
async def news(ticker: str, limit: int = Query(default=8, ge=1, le=20)) -> dict:
    try:
        return await run_in_threadpool(fetch_news, ticker.upper().strip(), limit)
    except Exception as error:
        raise unavailable(error) from error


@app.get("/api/v1/events/{ticker}")
async def events(ticker: str) -> dict:
    try:
        return await run_in_threadpool(fetch_upcoming_events, ticker.upper().strip())
    except Exception as error:
        raise unavailable(error) from error


@app.post("/api/v1/portfolio")
async def portfolio(request: PortfolioRequest) -> dict:
    try:
        positions = [position.model_dump() for position in request.positions]
        return await run_in_threadpool(calculate_portfolio, positions, request.confidence)
    except Exception as error:
        raise unavailable(error) from error


@app.post("/api/v1/backtests")
async def backtest(request: BacktestRequest) -> dict:
    try:
        if request.engine == "sma":
            return await run_in_threadpool(
                run_sma_backtest,
                request.ticker,
                request.short_window,
                request.long_window,
                request.transaction_cost_bps,
                request.slippage_bps,
                request.use_regime_filter,
                request.asset_class,
                request.position_mode,
                request.risk_free_rate,
                request.lookback_years,
            )

        from src.advanced_backtester import MLQuantBacktester

        start_year = datetime.now(timezone.utc).year - request.lookback_years
        engine = await run_in_threadpool(
            MLQuantBacktester,
            request.ticker,
            f"{start_year}-01-01",
            None,
            None,
            request.asset_class,
        )
        result = await run_in_threadpool(
            engine.run_walk_forward_xgboost,
            request.train_window,
            request.test_window,
            request.use_regime_filter,
            request.validation_fraction,
            request.transaction_cost_bps,
            request.n_trials,
            request.engine,
            request.target_horizon,
            request.long_threshold,
            request.short_threshold,
            request.position_mode,
            request.slippage_bps,
            request.risk_free_rate,
        )
        series = result.pop("data")
        result["series"] = [
            {
                "date": row.Date.isoformat(),
                "close": float(row.Close),
                "market": float(row.Cumulative_Market),
                "strategy": float(row.Cumulative_Strategy),
                "signal": int(row.ML_Signal),
                "probability": float(row.Model_Probability),
                "position": float(row.Position),
                "turnover": float(row.Turnover),
                "drawdown": float(row.Drawdown * 100),
                "strategy_return": float(row.Strategy_Return * 100),
            }
            for row in series.itertuples(index=False)
        ]
        result["classification"] = "simulated"
        result["data_status"] = "available"
        return result
    except Exception as error:
        raise unavailable(error) from error


@app.post("/api/v1/analysis")
async def analysis(request: AnalysisRequest) -> dict:
    try:
        from src.agent_manager import TradingAgentManager

        manager = TradingAgentManager()

        def require_local_model() -> None:
            try:
                response = requests.get(f"{manager.host}/api/tags", timeout=3)
                response.raise_for_status()
            except requests.RequestException as error:
                raise RuntimeError(
                    "The configured local Ollama service is unavailable."
                ) from error

        await run_in_threadpool(require_local_model)
        report = await run_in_threadpool(
            manager.analyze_stock, request.ticker, request.model
        )
        if any("Connection Error" in str(value) for value in report.values()):
            raise RuntimeError("The configured local Ollama model is unavailable.")
        return {
            "data_status": "available",
            "classification": "generated",
            "model": manager.model,
            "ticker": request.ticker,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "report": report,
            "limitations": [
                "Generated research can be incomplete or wrong.",
                "This is not investment advice and is not connected to a broker.",
            ],
        }
    except Exception as error:
        raise unavailable(error) from error


# Production keeps the static client in its own Nginx container. This opt-in
# mount exists only for local development and browser QA when Docker is absent.
from pathlib import Path

from fastapi.staticfiles import StaticFiles

project_root = Path(__file__).resolve().parents[2]
app.mount("/media", StaticFiles(directory=project_root / "assets"), name="media")

if os.getenv("HERMES_SERVE_FRONTEND") == "1":
    frontend_dir = project_root / "frontend"
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
