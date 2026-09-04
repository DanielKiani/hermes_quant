"""Data adapters for the API. No UI framework imports belong here."""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
import os
from pathlib import Path
import time
from typing import Any

import numpy as np
import pandas as pd
import requests
import yfinance as yf


ALLOWED_PERIODS = {"1mo", "3mo", "6mo", "1y", "2y", "5y"}
ASSET_CLASSES = {"equity", "crypto"}
CACHE_DIR = Path(os.getenv("HERMES_CACHE_DIR", "data/yfinance_cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)
yf.set_tz_cache_location(str(CACHE_DIR.resolve()))


def _number(value: Any) -> float | None:
    try:
        number = float(value)
        return number if np.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _cache_bucket(seconds: int = 300) -> int:
    return int(time.time() // seconds)


@lru_cache(maxsize=256)
def _history_cached(ticker: str, period: str, _bucket: int) -> pd.DataFrame:
    frame = pd.DataFrame()
    for attempt in range(3):
        frame = yf.Ticker(ticker).history(period=period, auto_adjust=True)
        if not frame.empty and "Close" in frame:
            break
        if attempt < 2:
            time.sleep(1.5 * (attempt + 1))
    if frame.empty or "Close" not in frame:
        raise ValueError(f"No observed market data returned for {ticker} after 3 attempts.")
    frame = frame.reset_index()
    frame["Date"] = pd.to_datetime(frame["Date"], utc=True)
    return frame


def _history(ticker: str, period: str) -> pd.DataFrame:
    return _history_cached(ticker, period, _cache_bucket()).copy(deep=True)


@lru_cache(maxsize=128)
def _instrument_info(ticker: str, _bucket: int) -> dict:
    try:
        return dict(yf.Ticker(ticker).get_info() or {})
    except Exception:
        return {}


def _timestamp(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    return None if pd.isna(parsed) else parsed.isoformat()


def fetch_terminal_snapshot(ticker: str, period: str = "6mo") -> dict:
    ticker = ticker.strip().upper()
    if not ticker:
        raise ValueError("Ticker is required.")
    if period not in ALLOWED_PERIODS:
        raise ValueError(f"Unsupported period: {period}.")

    fetched_at = datetime.now(timezone.utc).isoformat()
    instrument = yf.Ticker(ticker)
    history = _history(ticker, period)
    close = history["Close"].astype(float)
    volume = history.get("Volume", pd.Series(0, index=history.index)).fillna(0)
    returns = close.pct_change()
    sma_20 = close.rolling(20).mean()
    sma_50 = close.rolling(50).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rsi = 100 - (100 / (1 + (gain / loss.replace(0, np.nan))))

    latest = _number(close.iloc[-1])
    previous = _number(close.iloc[-2]) if len(close) > 1 else None
    change = (
        ((latest - previous) / previous) * 100
        if latest is not None and previous not in (None, 0)
        else None
    )

    try:
        fast_info = dict(instrument.fast_info)
    except Exception:
        fast_info = {}
    info = _instrument_info(ticker, _cache_bucket(900))
    quote_type = str(info.get("quoteType") or "Unknown")
    asset_class = "crypto" if quote_type.upper() == "CRYPTOCURRENCY" or ticker.endswith("-USD") else "equity"
    annualization_factor = 365 if asset_class == "crypto" else 252
    rolling_peak = close.cummax()
    period_drawdown = (close / rolling_peak) - 1

    points = []
    for index, row in history.iterrows():
        points.append(
            {
                "date": row["Date"].isoformat(),
                "open": _number(row.get("Open")),
                "high": _number(row.get("High")),
                "low": _number(row.get("Low")),
                "close": _number(row["Close"]),
                "volume": _number(volume.iloc[index]),
                "sma20": _number(sma_20.iloc[index]),
                "sma50": _number(sma_50.iloc[index]),
                "rsi": _number(rsi.iloc[index]),
            }
        )

    return {
        "data_status": "available",
        "classification": "observed",
        "source": "Yahoo Finance via yfinance",
        "freshness": "provider-delayed; not an exchange feed",
        "fetched_at": fetched_at,
        "ticker": ticker,
        "name": info.get("shortName") or info.get("longName") or ticker,
        "currency": fast_info.get("currency") or info.get("currency") or "USD",
        "exchange": fast_info.get("exchange") or info.get("exchange") or "Unknown",
        "quote_type": quote_type,
        "asset_class": asset_class,
        "annualization_factor": annualization_factor,
        "price": latest,
        "change_percent": change,
        "period": period,
        "metrics": {
            "period_high": _number(close.max()),
            "period_low": _number(close.min()),
            "average_volume": _number(volume.mean()),
            "annualized_volatility": _number(returns.std() * np.sqrt(annualization_factor) * 100),
            "momentum_30": _number(close.pct_change(30).iloc[-1] * 100),
            "period_max_drawdown": _number(period_drawdown.min() * 100),
            "rsi_14": _number(rsi.iloc[-1]),
            "sma_20": _number(sma_20.iloc[-1]),
            "sma_50": _number(sma_50.iloc[-1]),
            "market_cap": _number(info.get("marketCap")),
            "volume": _number(info.get("volume") or volume.iloc[-1]),
            "trailing_pe": _number(info.get("trailingPE")),
            "profit_margin": _number(info.get("profitMargins")),
            "return_on_equity": _number(info.get("returnOnEquity")),
            "beta": _number(info.get("beta")),
            "fifty_two_week_high": _number(info.get("fiftyTwoWeekHigh")),
            "fifty_two_week_low": _number(info.get("fiftyTwoWeekLow")),
            "circulating_supply": _number(info.get("circulatingSupply")),
            "max_supply": _number(info.get("maxSupply")),
        },
        "profile": {
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "country": info.get("country"),
            "website": info.get("website"),
            "description": info.get("longBusinessSummary") or info.get("description"),
        },
        "history": points,
    }


TAPE_SYMBOLS = {
    "equity": {
        "^GSPC": "S&P 500",
        "^DJI": "Dow 30",
        "^IXIC": "Nasdaq",
        "^RUT": "Russell 2000",
        "^VIX": "VIX",
        "^TNX": "10Y Treasury",
        "GC=F": "Gold",
        "DX-Y.NYB": "US Dollar",
    },
    "crypto": {
        "BTC-USD": "Bitcoin",
        "ETH-USD": "Ethereum",
        "SOL-USD": "Solana",
        "XRP-USD": "XRP",
        "BNB-USD": "BNB",
        "DOGE-USD": "Dogecoin",
        "ADA-USD": "Cardano",
    },
}

MOVER_NAMES = {
    "equity": {
        "NVDA": "NVIDIA",
        "TSLA": "Tesla",
        "AMD": "AMD",
        "META": "Meta",
        "SPY": "S&P 500 ETF",
        "QQQ": "Nasdaq 100 ETF",
        "AAPL": "Apple",
        "MSFT": "Microsoft",
        "AMZN": "Amazon",
        "COIN": "Coinbase",
    },
    "crypto": {
        "BTC-USD": "Bitcoin",
        "ETH-USD": "Ethereum",
        "SOL-USD": "Solana",
        "XRP-USD": "XRP",
        "BNB-USD": "BNB",
        "DOGE-USD": "Dogecoin",
        "ADA-USD": "Cardano",
        "AVAX-USD": "Avalanche",
        "LINK-USD": "Chainlink",
        "DOT-USD": "Polkadot",
        "SUI20947-USD": "Sui",
        "LTC-USD": "Litecoin",
        "BCH-USD": "Bitcoin Cash",
        "HBAR-USD": "Hedera",
        "XLM-USD": "Stellar",
        "TRX-USD": "TRON",
    },
}

MACRO_SYMBOLS = {
    "equity": {
        "^GSPC": "S&P 500",
        "^IXIC": "Nasdaq Composite",
        "^VIX": "Equity volatility (VIX)",
        "^TNX": "10Y Treasury",
    },
    "crypto": {
        "BTC-USD": "Bitcoin benchmark",
        "ETH-USD": "Ethereum benchmark",
        "DX-Y.NYB": "US Dollar",
        "^IXIC": "Nasdaq risk proxy",
        "GC=F": "Gold",
    },
}


@lru_cache(maxsize=8)
def _market_overview_cached(asset_class: str, _bucket: int) -> dict:
    if asset_class not in ASSET_CLASSES:
        raise ValueError(f"Unsupported asset class: {asset_class}.")
    tape_symbols = TAPE_SYMBOLS[asset_class]
    mover_names = MOVER_NAMES[asset_class]
    macro_symbols = MACRO_SYMBOLS[asset_class]
    context_symbols = list(dict.fromkeys([*tape_symbols, *macro_symbols]))
    context_data = yf.download(
        context_symbols,
        period="1mo",
        auto_adjust=True,
        group_by="ticker",
        progress=False,
        threads=True,
    )
    screener_quotes: dict[str, list[dict]] = {}
    if asset_class == "equity":
        for label, screen_id in {
            "trending": "most_actives",
            "gainers": "day_gainers",
            "losers": "day_losers",
        }.items():
            try:
                screener_quotes[label] = list(yf.screen(screen_id, count=6).get("quotes") or [])
            except Exception:
                screener_quotes[label] = []
    screen_symbols = [
        str(quote.get("symbol") or "").strip()
        for quotes in screener_quotes.values()
        for quote in quotes
        if quote.get("symbol")
    ]
    mover_symbols = list(dict.fromkeys([*screen_symbols, *mover_names]))
    mover_data = yf.download(
        mover_symbols,
        period="1mo",
        auto_adjust=True,
        group_by="ticker",
        progress=False,
        threads=True,
    )
    if context_data.empty and mover_data.empty:
        raise ValueError("Market overview provider returned no observations.")

    def close_series(symbol: str, data: pd.DataFrame) -> pd.Series:
        try:
            if isinstance(data.columns, pd.MultiIndex):
                if symbol in data.columns.get_level_values(0):
                    frame = data[symbol]
                else:
                    frame = data.xs(symbol, level=1, axis=1)
            else:
                frame = data
            return frame["Close"].dropna().astype(float)
        except (KeyError, TypeError):
            return pd.Series(dtype=float)

    def item(symbol: str, name: str, data: pd.DataFrame) -> dict | None:
        close = close_series(symbol, data)
        if len(close) < 2:
            return None
        change_value = close.iloc[-1] - close.iloc[-2]
        change = (change_value / close.iloc[-2]) * 100
        return {
            "ticker": symbol,
            "name": name,
            "price": float(close.iloc[-1]),
            "change_value": float(change_value),
            "change_percent": float(change),
            "history": [float(value) for value in close.tail(22)],
            "classification": "observed",
        }

    tape = [
        value
        for symbol, name in tape_symbols.items()
        if (value := item(symbol, name, context_data))
    ]
    movers = [
        value
        for symbol, name in mover_names.items()
        if (value := item(symbol, name, mover_data))
    ]
    ordered = sorted(movers, key=lambda value: value["change_percent"], reverse=True)
    mover_lookup = {value["ticker"]: value for value in movers}

    def screened_items(label: str) -> list[dict]:
        values = []
        for quote in screener_quotes.get(label, []):
            symbol = str(quote.get("symbol") or "").strip()
            if not symbol:
                continue
            observed = mover_lookup.get(symbol)
            if observed is None:
                price = _number(quote.get("regularMarketPrice"))
                change = _number(quote.get("regularMarketChangePercent"))
                if price is None or change is None:
                    continue
                observed = {
                    "ticker": symbol,
                    "name": quote.get("shortName") or quote.get("longName") or symbol,
                    "price": price,
                    "change_value": _number(quote.get("regularMarketChange")),
                    "change_percent": change,
                    "history": [],
                    "classification": "observed",
                }
            else:
                observed = {
                    **observed,
                    "name": quote.get("shortName") or quote.get("longName") or observed["name"],
                    "volume": _number(quote.get("regularMarketVolume")),
                }
            values.append(observed)
        return values[:5]

    fallback_groups = {
        "trending": sorted(movers, key=lambda value: abs(value["change_percent"]), reverse=True)[:5],
        "gainers": [value for value in ordered if value["change_percent"] > 0][:5],
        "losers": [value for value in reversed(ordered) if value["change_percent"] < 0][:5],
    }
    groups = {
        label: screened_items(label) or fallback_groups[label]
        for label in ("trending", "gainers", "losers")
    }
    macro = {
        symbol: value
        for symbol, name in macro_symbols.items()
        if (value := item(symbol, name, context_data))
    }
    return {
        "data_status": "available" if tape else "unavailable",
        "classification": "observed",
        "source": "Yahoo Finance via yfinance",
        "freshness": "provider-delayed; not an exchange feed",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "asset_class": asset_class,
        "tape": tape,
        "trending": groups["trending"],
        "gainers": groups["gainers"],
        "losers": groups["losers"],
        "mover_method": "Yahoo Finance most-active and day-mover screeners" if asset_class == "equity" and all(screener_quotes.values()) else "asset-class watchlist fallback",
        "macro": macro,
    }


def fetch_market_overview(asset_class: str = "equity") -> dict:
    asset_class = asset_class.strip().lower()
    return _market_overview_cached(asset_class, _cache_bucket()).copy()


def fetch_research_profile(asset_class: str) -> dict:
    asset_class = asset_class.strip().lower()
    if asset_class not in ASSET_CLASSES:
        raise ValueError(f"Unsupported asset class: {asset_class}.")
    if asset_class == "crypto":
        return {
            "asset_class": "crypto",
            "label": "Crypto",
            "default_ticker": "BTC-USD",
            "annualization_factor": 365,
            "calendar": "Continuous daily observations, including weekends",
            "regime_reference": "BTC-USD 200-day trend",
            "context_indicators": ["BTC", "ETH", "US Dollar", "Nasdaq", "Gold"],
            "options_policy": "Standard Yahoo spot tickers do not expose a listed options chain.",
            "backtest_defaults": {
                "transaction_cost_bps": 10.0,
                "slippage_bps": 5.0,
                "train_window": 1095,
                "test_window": 90,
                "target_horizon": 7,
                "long_threshold": 0.55,
                "short_threshold": 0.45,
            },
        }
    return {
        "asset_class": "equity",
        "label": "Equities",
        "default_ticker": "AAPL",
        "annualization_factor": 252,
        "calendar": "Exchange trading days",
        "regime_reference": "SPY 200-day trend",
        "context_indicators": ["S&P 500", "Nasdaq", "VIX", "10Y Treasury"],
        "options_policy": "Listed equity options are loaded only when requested.",
        "backtest_defaults": {
            "transaction_cost_bps": 5.0,
            "slippage_bps": 2.0,
            "train_window": 750,
            "test_window": 63,
            "target_horizon": 5,
            "long_threshold": 0.54,
            "short_threshold": 0.46,
        },
    }


def fetch_options_snapshot(ticker: str) -> dict:
    ticker = ticker.strip().upper()
    instrument = yf.Ticker(ticker)
    expirations = list(instrument.options or [])[:4]
    if not expirations:
        return {
            "data_status": "unavailable",
            "classification": "observed",
            "ticker": ticker,
            "message": "No standard listed options were returned for this asset.",
            "points": [],
        }

    points: list[dict] = []
    total_put_interest = 0.0
    total_call_interest = 0.0
    for expiration in expirations:
        chain = instrument.option_chain(expiration)
        total_put_interest += float(chain.puts.get("openInterest", pd.Series(dtype=float)).fillna(0).sum())
        total_call_interest += float(chain.calls.get("openInterest", pd.Series(dtype=float)).fillna(0).sum())
        calls = chain.calls.copy()
        if "volume" in calls:
            calls = calls.sort_values("volume", ascending=False, na_position="last")
        for _, row in calls.head(80).iterrows():
            implied_volatility = _number(row.get("impliedVolatility"))
            strike = _number(row.get("strike"))
            if implied_volatility is None or strike is None:
                continue
            points.append(
                {
                    "expiration": expiration,
                    "strike": strike,
                    "iv": implied_volatility,
                    "volume": _number(row.get("volume")),
                    "open_interest": _number(row.get("openInterest")),
                }
            )

    ratio = total_put_interest / total_call_interest if total_call_interest else None
    return {
        "data_status": "available" if points else "unavailable",
        "classification": "observed",
        "source": "Yahoo Finance listed-options metadata via yfinance",
        "freshness": "provider-delayed",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "ticker": ticker,
        "expirations": expirations,
        "put_call_ratio": _number(ratio),
        "points": points,
        "limitations": [
            "Displayed implied volatility is provider-supplied and may be stale.",
            "Only the first four listed expirations and the most active calls are shown.",
        ],
    }


def fetch_news(ticker: str, limit: int = 8) -> dict:
    fetched_at = datetime.now(timezone.utc).isoformat()
    try:
        raw_items = yf.Ticker(ticker).news or []
    except Exception:
        raw_items = []
    items = []
    for raw in raw_items[:limit]:
        if not isinstance(raw, dict):
            continue
        content = raw.get("content") or raw
        if not isinstance(content, dict):
            continue
        provider = content.get("provider") or {}
        canonical = content.get("canonicalUrl") or {}
        thumbnail = content.get("thumbnail") or {}
        items.append(
            {
                "title": content.get("title") or "Untitled report",
                "publisher": provider.get("displayName") or raw.get("publisher") or "Unknown",
                "url": canonical.get("url") or raw.get("link"),
                "published_at": _timestamp(content.get("pubDate") or raw.get("providerPublishTime")),
                "thumbnail": thumbnail.get("originalUrl"),
            }
        )
    return {
        "data_status": "available" if items else "unavailable",
        "classification": "observed",
        "source": "Yahoo Finance news metadata via yfinance",
        "fetched_at": fetched_at,
        "ticker": ticker,
        "items": items,
    }


@lru_cache(maxsize=128)
def _events_cached(ticker: str, _bucket: int) -> dict:
    ticker = ticker.strip().upper()
    fetched_at = datetime.now(timezone.utc)
    today = fetched_at.date()
    events: list[dict] = []
    sources: list[dict] = []

    try:
        calendar = dict(yf.Ticker(ticker).calendar or {})
    except Exception:
        calendar = {}

    event_labels = {
        "Earnings Date": ("earnings", "Estimated earnings / quarterly call"),
        "Ex-Dividend Date": ("dividend", "Ex-dividend date"),
        "Dividend Date": ("dividend", "Dividend payment date"),
    }
    for key, (kind, title) in event_labels.items():
        raw_values = calendar.get(key)
        values = raw_values if isinstance(raw_values, (list, tuple)) else [raw_values]
        for value in values:
            parsed = pd.to_datetime(value, utc=True, errors="coerce")
            if pd.isna(parsed) or parsed.date() < today:
                continue
            detail = None
            if kind == "earnings":
                low = _number(calendar.get("Earnings Low"))
                high = _number(calendar.get("Earnings High"))
                if low is not None and high is not None:
                    detail = f"Provider EPS estimate range: {low:.2f}–{high:.2f}"
            events.append(
                {
                    "date": parsed.date().isoformat(),
                    "title": title,
                    "detail": detail or f"Provider calendar event for {ticker}",
                    "kind": kind,
                    "ticker": ticker,
                    "classification": "observed",
                    "source": "Yahoo Finance calendar metadata",
                    "url": f"https://finance.yahoo.com/quote/{ticker}/",
                }
            )
    if calendar:
        sources.append({"name": "Yahoo Finance calendar metadata", "status": "available"})

    treasury_url = "https://www.treasurydirect.gov/TA_WS/securities/upcoming?format=json"
    try:
        response = requests.get(treasury_url, timeout=8)
        response.raise_for_status()
        securities = response.json()
        for security in securities:
            parsed = pd.to_datetime(security.get("auctionDate"), utc=True, errors="coerce")
            if pd.isna(parsed) or parsed.date() < today:
                continue
            term = str(security.get("securityTerm") or "Treasury").strip()
            security_type = str(security.get("securityType") or "security").strip()
            events.append(
                {
                    "date": parsed.date().isoformat(),
                    "title": f"U.S. Treasury {term} {security_type} auction",
                    "detail": f"Settlement {str(security.get('issueDate') or '')[:10] or 'not provided'} · CUSIP {security.get('cusip') or 'pending'}",
                    "kind": "treasury",
                    "ticker": None,
                    "classification": "observed",
                    "source": "U.S. TreasuryDirect upcoming securities API",
                    "url": "https://www.treasurydirect.gov/auctions/upcoming/",
                }
            )
        sources.append({"name": "U.S. TreasuryDirect upcoming securities API", "status": "available"})
    except Exception:
        sources.append({"name": "U.S. TreasuryDirect upcoming securities API", "status": "unavailable"})

    unique: dict[tuple[str, str], dict] = {}
    for event in events:
        unique[(event["date"], event["title"])] = event
    ordered = sorted(unique.values(), key=lambda event: (event["date"], event["title"]))[:40]
    return {
        "data_status": "available" if ordered else "unavailable",
        "classification": "observed",
        "ticker": ticker,
        "fetched_at": fetched_at.isoformat(),
        "events": ordered,
        "sources": sources,
        "limitations": [
            "Provider dates can change; verify the linked primary or issuer source before acting.",
            "This calendar is selective, not a complete global macroeconomic calendar.",
        ],
    }


def fetch_upcoming_events(ticker: str) -> dict:
    return _events_cached(ticker, _cache_bucket(1800)).copy()


def calculate_portfolio(positions: list[dict], confidence: float) -> dict:
    tickers = [position["ticker"] for position in positions]
    quantities = {position["ticker"]: position["quantity"] for position in positions}
    price_series: dict[str, pd.Series] = {}

    for ticker in tickers:
        history = _history(ticker, "1y").set_index("Date")["Close"].astype(float)
        price_series[ticker] = history

    prices = pd.concat(price_series, axis=1).dropna()
    if len(prices) < 30:
        raise ValueError("At least 30 aligned observations are required for portfolio risk.")

    holdings = []
    total_value = 0.0
    for ticker in tickers:
        price = float(prices[ticker].iloc[-1])
        value = price * quantities[ticker]
        total_value += value
        holdings.append(
            {"ticker": ticker, "quantity": quantities[ticker], "price": price, "value": value}
        )
    for holding in holdings:
        holding["weight"] = holding["value"] / total_value if total_value else 0

    weights = np.array([next(h["weight"] for h in holdings if h["ticker"] == t) for t in tickers])
    portfolio_returns = prices.pct_change().dropna().dot(weights)
    percentile = (1 - confidence) * 100
    var_percent = max(0.0, -float(np.percentile(portfolio_returns, percentile)) * 100)

    correlation = prices.pct_change().dropna().corr()
    return {
        "data_status": "available",
        "classification": "derived",
        "source": "Derived from provider-delayed adjusted closes",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "total_value": total_value,
        "confidence": confidence,
        "historical_var_percent": var_percent,
        "historical_var_value": total_value * var_percent / 100,
        "holdings": holdings,
        "correlation": {
            "labels": tickers,
            "values": correlation.round(4).values.tolist(),
        },
        "limitations": [
            "Historical one-day VaR is an estimate, not a maximum possible loss.",
            "Prices may be delayed and positions are stored only in this browser.",
        ],
    }


def run_sma_backtest(
    ticker: str,
    short_window: int,
    long_window: int,
    transaction_cost_bps: float,
    slippage_bps: float,
    use_regime_filter: bool,
    asset_class: str,
    position_mode: str,
    risk_free_rate: float,
    lookback_years: int,
) -> dict:
    period = "5y" if lookback_years <= 5 else "max"
    history = _history(ticker, period).copy()
    cutoff = pd.Timestamp.now(tz="UTC") - pd.DateOffset(years=lookback_years)
    history = history.loc[history["Date"] >= cutoff].reset_index(drop=True)
    close = history["Close"].astype(float)
    history["Returns"] = close.pct_change()
    history["Short_SMA"] = close.rolling(short_window).mean()
    history["Long_SMA"] = close.rolling(long_window).mean()
    short_signal = -1 if position_mode == "long_short" else 0
    history["Signal"] = np.where(
        history["Short_SMA"] > history["Long_SMA"], 1, short_signal
    )

    if use_regime_filter:
        reference_symbol = "BTC-USD" if asset_class == "crypto" else "SPY"
        reference = _history(reference_symbol, period)[["Date", "Close"]].rename(
            columns={"Close": "Reference_Close"}
        )
        reference["Reference_SMA_200"] = reference["Reference_Close"].rolling(200).mean()
        history = history.merge(reference, on="Date", how="left")
        bear = history["Reference_Close"] < history["Reference_SMA_200"]
        history.loc[bear.fillna(False) & (history["Signal"] > 0), "Signal"] = 0

    history = history.dropna(subset=["Returns", "Long_SMA"]).reset_index(drop=True)
    if history.empty:
        raise ValueError("Not enough observations for the requested SMA windows.")
    position = history["Signal"].shift(1).fillna(0)
    turnover = position.diff().abs().fillna(position.abs())
    cost = turnover * ((transaction_cost_bps + slippage_bps) / 10_000)
    history["Strategy_Return"] = position * history["Returns"] - cost
    history["Cumulative_Market"] = (1 + history["Returns"]).cumprod()
    history["Cumulative_Strategy"] = (1 + history["Strategy_Return"]).cumprod()
    history["Position"] = position
    history["Turnover"] = turnover
    history["Drawdown"] = (
        history["Cumulative_Strategy"] / history["Cumulative_Strategy"].cummax() - 1
    )
    strategy_return = (history["Cumulative_Strategy"].iloc[-1] - 1) * 100
    market_return = (history["Cumulative_Market"].iloc[-1] - 1) * 100
    annual_factor = 365 if asset_class == "crypto" else 252
    sample_years = len(history) / annual_factor
    cagr = (
        history["Cumulative_Strategy"].iloc[-1] ** (1 / sample_years) - 1
        if sample_years > 0 and history["Cumulative_Strategy"].iloc[-1] > 0
        else -1.0
    )
    volatility = history["Strategy_Return"].std() * np.sqrt(annual_factor)
    daily_risk_free = (1 + risk_free_rate / 100) ** (1 / annual_factor) - 1
    excess = history["Strategy_Return"] - daily_risk_free
    sharpe = (
        excess.mean() * annual_factor / volatility
        if volatility > 0
        else 0.0
    )
    downside = history.loc[history["Strategy_Return"] < 0, "Strategy_Return"].std()
    sortino = excess.mean() * annual_factor / (downside * np.sqrt(annual_factor)) if downside > 0 else 0.0
    max_drawdown = history["Drawdown"].min() * 100
    calmar = cagr / abs(max_drawdown / 100) if max_drawdown < 0 else 0.0
    active = position != 0
    hit_rate = (history.loc[active, "Strategy_Return"] > 0).mean() * 100 if active.any() else 0.0

    return {
        "data_status": "available",
        "classification": "simulated",
        "Return_Pct": float(strategy_return),
        "Market_Return_Pct": float(market_return),
        "Sharpe_Ratio": float(sharpe),
        "Sortino_Ratio": float(sortino),
        "Calmar_Ratio": float(calmar),
        "Annualized_Return_Pct": float(cagr * 100),
        "Annualized_Volatility_Pct": float(volatility * 100),
        "Max_Drawdown_Pct": float(max_drawdown),
        "Total_Trades": int((turnover > 0).sum()),
        "Turnover": float(turnover.sum()),
        "Exposure_Pct": float(position.abs().mean() * 100),
        "Hit_Rate_Pct": float(hit_rate),
        "Total_Cost_Pct": float(cost.sum() * 100),
        "series": [
            {
                "date": row.Date.isoformat(),
                "close": float(row.Close),
                "market": float(row.Cumulative_Market),
                "strategy": float(row.Cumulative_Strategy),
                "signal": int(row.Signal),
                "position": float(row.Position),
                "turnover": float(row.Turnover),
                "drawdown": float(row.Drawdown * 100),
                "strategy_return": float(row.Strategy_Return * 100),
            }
            for row in history.itertuples(index=False)
        ],
        "evidence": {
            "ticker": ticker,
            "engine": "fixed-parameter SMA crossover",
            "asset_class": asset_class,
            "annualization_factor": annual_factor,
            "selection_rule": "User-supplied parameters; no in-sample optimization performed",
            "short_window": short_window,
            "long_window": long_window,
            "transaction_cost_bps": transaction_cost_bps,
            "slippage_bps": slippage_bps,
            "position_mode": position_mode,
            "risk_free_rate_percent": risk_free_rate,
            "lookback_years": lookback_years,
            "regime_filter": use_regime_filter,
            "regime_reference": "BTC-USD 200-day trend" if asset_class == "crypto" else "SPY 200-day trend",
            "folds": [],
            "limitations": [
                "Historical daily-close simulation; not live or broker-executed performance.",
                "Configured costs and slippage are deterministic; spread variation and market impact are excluded.",
                "Short borrow availability, funding, taxes, and corporate actions beyond adjusted prices are excluded.",
            ],
        },
    }
