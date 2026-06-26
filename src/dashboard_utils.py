import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from ddgs import DDGS
from data_loader import download_daily_data
import re

@st.cache_data(ttl=300, show_spinner="Fetching Market Movers...") 
def fetch_market_movers():
    tickers = ["NVDA", "TSLA", "AMD", "META", "SPY", "QQQ", "BTC-USD", "AAPL", "MSFT", "AMZN", "COIN"]
    names_map = {
        "NVDA": "NVIDIA Corp.", "TSLA": "Tesla, Inc.", "AMD": "Advanced Micro Devices", 
        "META": "Meta Platforms", "SPY": "SPDR S&P 500", "QQQ": "Invesco QQQ",
        "BTC-USD": "Bitcoin", "AAPL": "Apple Inc.", "MSFT": "Microsoft", 
        "AMZN": "Amazon.com", "COIN": "Coinbase Global"
    }
    data = []
    for t in tickers:
        try:
            tick = yf.Ticker(t)
            hist = tick.history(period="5d")
            short_name = names_map.get(t, t)
            if not hist.empty and len(hist) >= 2:
                latest = float(hist['Close'].iloc[-1])
                prev = float(hist['Close'].iloc[-2])
                pct_change = ((latest - prev) / prev) * 100
                data.append({"ticker": t, "name": short_name, "price": latest, "change": pct_change, "history": hist['Close'].tolist()})
        except Exception:
            continue
    sorted_data = sorted(data, key=lambda x: x['change'], reverse=True)
    gainers = [x for x in sorted_data if x['change'] > 0][:3]
    losers = [x for x in sorted_data if x['change'] < 0][::-1][:3]
    trending = sorted_data[:3]
    return gainers, losers, trending

@st.cache_data(ttl=300, show_spinner=False)
def fetch_top_bar_data():
    """Fetches data for the clickable Macro Ticker Tape at the top of the dashboard."""
    tickers = {
        "^DJI": "Dow 30", 
        "^IXIC": "Nasdaq", 
        "^RUT": "Russell 2000", 
        "^VIX": "VIX", 
        "GC=F": "Gold", 
        "BTC-USD": "Bitcoin", 
        "CL=F": "Crude Oil"
    }
    data = []
    for t, name in tickers.items():
        try:
            tick = yf.Ticker(t)
            hist = tick.history(period="5d")
            if not hist.empty and len(hist) >= 2:
                latest = float(hist['Close'].iloc[-1])
                prev = float(hist['Close'].iloc[-2])
                pct_change = ((latest - prev) / prev) * 100
                data.append({"ticker": t, "name": name, "price": latest, "change": pct_change, "history": hist['Close'].tolist()})
        except Exception:
            continue
    return data

@st.cache_data(ttl=60, show_spinner=False)
def fetch_portfolio_prices(tickers):
    data = {}
    if not tickers: return data
    for t in tickers:
        try:
            tick = yf.Ticker(t)
            hist = tick.history(period="5d")
            if len(hist) >= 2:
                data[t] = {
                    'price': float(hist['Close'].iloc[-1]),
                    'prev_price': float(hist['Close'].iloc[-2])
                }
        except Exception: pass
    return data

@st.cache_data(ttl=300, show_spinner=False)
def get_ticker_metadata(t):
    return yf.Ticker(t).info

@st.cache_data(ttl=300, show_spinner=False)
def get_options_data(t):
    try:
        tick = yf.Ticker(t)
        expirations = tick.options
        if not expirations: return None
        chain = tick.option_chain(expirations[0])
        puts = chain.puts['openInterest'].sum()
        calls = chain.calls['openInterest'].sum()
        if calls == 0: return None
        return puts / calls
    except Exception:
        return None

@st.cache_data(ttl=300, show_spinner=False)
def get_volatility_surface(t):
    try:
        tick = yf.Ticker(t)
        expirations = tick.options
        if not expirations: return None
        
        dates = expirations[:4] 
        surface_data = []
        for d in dates:
            chain = tick.option_chain(d)
            calls = chain.calls
            calls = calls[calls['volume'] > 0] 
            for _, row in calls.iterrows():
                surface_data.append({
                    'Expiration': d,
                    'Strike': row['strike'],
                    'IV': row['impliedVolatility']
                })
        if not surface_data: return None
        return pd.DataFrame(surface_data)
    except Exception:
        return None

@st.cache_data(ttl=300, show_spinner=False)
def get_ticker_history_max(t):
    return yf.Ticker(t).history(period="max")

@st.cache_data(ttl=300, show_spinner=False)
def get_daily_data_cached(ticker, period="max"):
    return download_daily_data(ticker, period=period)

@st.cache_data(ttl=300, show_spinner=False)
def get_news_cached(t):
    news_items = []
    try:
        with DDGS() as ddgs:
            news_items = list(ddgs.news(t, max_results=8))
    except Exception: pass
    return news_items

@st.cache_data(ttl=300, show_spinner=False)
def get_general_news_cached():
    """Fetches broad market and financial news for the general tab."""
    news_items = []
    try:
        with DDGS() as ddgs:
            news_items = list(ddgs.news("stock market OR finance OR economy", max_results=12))
    except Exception: pass
    return news_items

@st.cache_data(ttl=3600, show_spinner=False)
def get_macro_data():
    try:
        sp500 = yf.Ticker("^GSPC").history(period="5d")
        tnx = yf.Ticker("^TNX").history(period="5d")
        return {
            "SP500": {"price": sp500['Close'].iloc[-1], "change": (sp500['Close'].iloc[-1]/sp500['Close'].iloc[-2] - 1)*100},
            "TNX": {"price": tnx['Close'].iloc[-1], "change": (tnx['Close'].iloc[-1]/tnx['Close'].iloc[-2] - 1)*100}
        }
    except:
        return None

@st.cache_data(ttl=86400, show_spinner=False)
def get_upcoming_earnings(ticker):
    try:
        tick = yf.Ticker(ticker)
        dates = tick.get_earnings_dates(limit=3)
        if dates is not None and not dates.empty:
            future_dates = dates[dates.index > pd.Timestamp.now(tz=dates.index.tz)]
            if not future_dates.empty:
                return future_dates.index[0].strftime('%B %d, %Y')
        return "No upcoming dates scheduled."
    except:
        return "Data unavailable."

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_correlation_matrix(tickers):
    if not tickers or len(tickers) < 2: return None
    try:
        data = yf.download(tickers, period="1y", progress=False)['Close']
        if isinstance(data, pd.Series): return None 
        returns = data.pct_change().dropna()
        return returns.corr()
    except Exception:
        return None

@st.cache_data(ttl=3600, show_spinner=False)
def calculate_portfolio_var(portfolio_dict, confidence=0.95):
    if not portfolio_dict: return 0.0
    try:
        tickers = list(portfolio_dict.keys())
        data = yf.download(tickers, period="1y", progress=False)['Close']
        
        if len(tickers) == 1:
            if isinstance(data, pd.DataFrame): data = data.iloc[:, 0]
            returns = data.pct_change().dropna()
            return np.percentile(returns, (1 - confidence) * 100)
            
        else:
            returns = data.pct_change().dropna()
            valid_tickers = [t for t in returns.columns if t in portfolio_dict]
            prices = data[valid_tickers].iloc[-1]
            values = np.array([prices[t] * portfolio_dict[t] for t in valid_tickers])
            
            total_val = np.sum(values)
            if total_val == 0: return 0.0
            
            weights = values / total_val
            port_returns = returns[valid_tickers].dot(weights)
            return np.percentile(port_returns, (1 - confidence) * 100)
    except Exception:
        return 0.0

def parse_pm_verdict(text):
    matches = re.findall(r'FINAL DECISION:\s*\*?\*?\s*(BUY|SELL|HOLD)', text, re.IGNORECASE)
    decision = "HOLD" 
    if matches:
        decision = matches[-1].upper()
    return text, decision