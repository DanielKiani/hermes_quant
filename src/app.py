import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys
import os
import datetime
import pandas as pd
import yfinance as yf
import numpy as np

current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = current_dir if os.path.basename(current_dir) == "src" else os.path.join(current_dir, "src")
sys.path.append(src_dir)

from agent_manager import TradingAgentManager
from dashboard_utils import (
    fetch_market_movers, fetch_portfolio_prices, get_ticker_metadata, 
    get_options_data, get_volatility_surface, get_ticker_history_max, 
    get_daily_data_cached, get_news_cached, get_general_news_cached, parse_pm_verdict,
    get_macro_data, get_upcoming_earnings, fetch_correlation_matrix, calculate_portfolio_var, fetch_top_bar_data
)
from ui_styles import get_custom_css

# --- PAGE CONFIG ---
st.set_page_config(page_title="Hermes Quant Terminal", layout="wide", page_icon="🏛️", initial_sidebar_state="collapsed")

# --- INIT SESSION STATE ---
if 'show_full_about' not in st.session_state: st.session_state.show_full_about = False
if 'current_ticker' not in st.session_state: st.session_state.current_ticker = "AAPL"
if 'run_ai' not in st.session_state: st.session_state.run_ai = False
if 'ai_report' not in st.session_state: st.session_state.ai_report = None
if 'ml_choice' not in st.session_state: st.session_state.ml_choice = "XGBoost Walk-Forward ML"
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = {"AAPL": 15.5, "BTC-USD": 0.25, "NVDA": 40.0}
if 'nav_tab' not in st.session_state: st.session_state.nav_tab = "Market Analysis"

# Load Custom CSS
st.markdown(get_custom_css(), unsafe_allow_html=True)

# --- CSS OVERRIDES FOR UI FIXES & YAHOO STYLING ---
st.markdown("""
<style>
    /* Hide Streamlit Native Top Bar */
    header[data-testid="stHeader"] { display: none !important; }
    div[data-testid="stToolbar"] { display: none !important; }

    /* 1. Force Restore Radio Button Dots (ML Selector & Timeframes) */
    div[role="radiogroup"] label > div:first-child { display: flex !important; }
    div[role="radiogroup"] label [data-testid="stMarkdownContainer"] { margin-left: 5px; }
    
    /* 2. Style the top navigation buttons to act like elegant pill tabs */
    button[kind="secondary"] { border: 1px solid transparent !important; background-color: transparent !important; color: #8A919E !important; font-weight: 500 !important; transition: all 0.2s; }
    button[kind="secondary"]:hover { color: #F3F5F7 !important; background-color: rgba(255,255,255,0.05) !important; border-radius: 20px !important; }
    button[kind="primary"] { border: 1px solid #0052FF !important; border-radius: 20px !important; background-color: #0052FF !important; color: #ffffff !important; font-weight: bold !important; box-shadow: 0 4px 6px rgba(0, 82, 255, 0.2) !important; }
    
    /* 3. Aggressively miniaturize the Top Macro Ticker Tape buttons to match Yahoo Finance */
    button[kind="tertiary"] { padding: 0px !important; min-height: 0px !important; font-size: 13px !important; font-weight: 700 !important; color: #7fcfff !important; line-height: 1.2 !important; margin-bottom: 2px !important; background: transparent !important; border: none !important;}
    button[kind="tertiary"]:hover { color: #ffffff !important; text-decoration: underline !important; }
    
    /* Custom Aesthetics */
    .left-static-header { background-color: #171924; padding: 16px; margin-bottom: 15px; border: 1px solid #222531; border-radius: 8px; }
    .small-info-box { background-color: #171924; border: 1px solid #222531; border-radius: 8px; padding: 12px; }
    .small-info-label { color: #8A919E; font-size: 11px; margin-bottom: 4px; }
    .small-info-val { color: #F3F5F7; font-size: 13px; font-weight: 600; }
    .perf-bar-bg { height: 4px; background-color: #2B2C33; border-radius: 2px; position: relative; margin-top: 8px; margin-bottom: 8px; }
    .perf-dot { position: absolute; top: -3px; width: 10px; height: 10px; background-color: #F3F5F7; border-radius: 50%; box-shadow: 0 0 4px rgba(0,0,0,0.5); }
    .movers-header { font-size: 14px; font-weight: 700; color: #F3F5F7; margin-top: 15px; margin-bottom: 10px; padding-bottom: 4px; border-bottom: 1px solid #222531; }
    .news-link { color: #F3F5F7; text-decoration: none; font-weight: 600; font-size: 13px; display: block; margin-bottom: 4px; }
    .news-link:hover { color: #0052FF; text-decoration: none; }
    .news-meta { color: #8A919E; font-size: 10px; }
    div[data-testid="stTextInput"] input { background-color: #171924; border: 1px solid #222531; border-radius: 20px; padding-left: 15px; color: #F3F5F7; height: 38px; }
    div[data-testid="stTextInput"] input:focus { border-color: #0052FF; box-shadow: none; }
    .vertical-line { position: absolute; left: -1rem; top: 0; width: 1px; height: 100%; min-height: 850px; background-color: #222531; z-index: 0; }
    div[data-testid="stVerticalBlock"] > div[style*="border"] { background-color: #171924; border-color: #222531 !important; border-radius: 12px; }
    hr { border-color: #222531 !important; margin: 10px 0 !important; }
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def load_agent(): return TradingAgentManager()
agent = load_agent()

# ==========================================
# YAHOO-STYLE HEADER & TIGHT NAVIGATION
# ==========================================
st.markdown('<div id="sticky-nav"></div>', unsafe_allow_html=True)

# Using spacer columns to pack the nav buttons tightly on the right!
col_logo, col_search, col_spacer, n1, n2, n3, n4 = st.columns([2, 3, 1, 1.2, 0.8, 1, 1.2], vertical_alignment="center")

with col_logo: 
    # Make sure hermes_banner.png is saved in the same directory as app.py!
    try:
        st.image("assets/hermes_banner.png", use_container_width=True)
    except Exception:
        # Fallback text if the image isn't found
        st.markdown("<h3 style='margin: 0px; color: #F3F5F7;'>🏛️ Hermes Quant</h3>", unsafe_allow_html=True)

with col_search:
    ticker_input = st.text_input("Search Asset:", value=st.session_state.current_ticker, label_visibility="collapsed", placeholder="🔍 Search Asset (e.g., AAPL, BTC-USD)").upper()
    if ticker_input != st.session_state.current_ticker:
        st.session_state.current_ticker = ticker_input
        st.session_state.run_ai = False
        st.session_state.ai_report = None
        st.session_state.show_full_about = False
        st.rerun()
    ticker = st.session_state.current_ticker

# Tight Nav Buttons
def set_nav(tab_name):
    st.session_state.nav_tab = tab_name

with n1: st.button("Market Analysis", type="primary" if st.session_state.nav_tab=="Market Analysis" else "secondary", on_click=set_nav, args=("Market Analysis",), width="stretch")
with n2: st.button("News", type="primary" if st.session_state.nav_tab=="News" else "secondary", on_click=set_nav, args=("News",), width="stretch")
with n3: st.button("Portfolio", type="primary" if st.session_state.nav_tab=="My Portfolio" else "secondary", on_click=set_nav, args=("My Portfolio",), width="stretch")
with n4: st.button("Quant Academy", type="primary" if st.session_state.nav_tab=="Quant Academy" else "secondary", on_click=set_nav, args=("Quant Academy",), width="stretch")

st.markdown("<hr style='margin: 10px 0 5px 0; border-color: #222531;'>", unsafe_allow_html=True)

# ==========================================
# MINIATURIZED TOP MACRO TICKER TAPE (Stacked Layout!)
# ==========================================
top_bar_data = fetch_top_bar_data()
if top_bar_data:
    cols = st.columns(len(top_bar_data))
    for i, item in enumerate(top_bar_data):
        with cols[i]:
            i_color = "#00D395" if item['change'] >= 0 else "#FF4C4A"
            i_arrow = "+" if item['change'] >= 0 else ""
            
            # 1. Chart ON TOP
            spark = go.Figure(go.Scatter(y=item['history'], mode='lines', line=dict(color=i_color, width=2.0)))
            spark.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(l=0, r=0, t=0, b=0), height=35, xaxis=dict(visible=False), yaxis=dict(visible=False), showlegend=False, hovermode=False)
            st.plotly_chart(spark, config={'displayModeBar': False}, width="stretch", key=f"top_spark_{item['ticker']}")

            # 2. Button and Text UNDERNEATH
            if st.button(item['name'], key=f"top_btn_{item['ticker']}", type="tertiary", help=f"Analyze {item['name']}"):
                st.session_state.current_ticker = item['ticker']
                st.session_state.nav_tab = "Market Analysis"
                st.rerun()
                
            st.markdown(f"<div style='line-height: 1.3; margin-top: 0px;'><span style='font-weight: 700; color: #F3F5F7; font-size: 13px;'>{item['price']:,.2f}</span><br><span style='color: {i_color}; font-size: 11px; font-weight: 600;'>{i_arrow}{item['change']:.2f}%</span></div>", unsafe_allow_html=True)

st.markdown("<hr style='margin: 5px 0 15px 0; border-color: #222531;'>", unsafe_allow_html=True)

# --- LEGAL DISCLAIMER ---
st.markdown("""
<div style="background-color: rgba(245, 176, 40, 0.1); border: 1px solid rgba(245, 176, 40, 0.3); border-radius: 8px; padding: 10px; margin-bottom: 15px;">
    <span style="color: #F5B028; font-weight: bold; font-size: 12px;">⚠️ Legal Disclaimer:</span> 
    <span style="color: #8A919E; font-size: 12px;">This application and its AI-generated analyses, verdicts, and quantitative forecasts are for educational and informational purposes only. They do not constitute financial or investment advice.</span>
</div>
""", unsafe_allow_html=True)

# ==========================================
# PAGE ROUTER
# ==========================================

if st.session_state.nav_tab == "Market Analysis":
    if ticker:
        try:
            df_full = get_daily_data_cached(ticker, period="max") 
            
            # Crypto Fallback System
            is_crypto_or_commodity = False
            if df_full.empty and not ticker.endswith("-USD"):
                alt_ticker = f"{ticker}-USD"
                df_alt = get_daily_data_cached(alt_ticker, period="max")
                if not df_alt.empty:
                    ticker = alt_ticker
                    df_full = df_alt
                    
            if "-" in ticker or "=F" in ticker:
                is_crypto_or_commodity = True
            
            info = get_ticker_metadata(ticker)
            df_max = get_ticker_history_max(ticker)
            put_call_ratio = get_options_data(ticker)
            
            if not df_full.empty and len(df_full) >= 2:
                latest_close = df_full['Close'].iloc[-1]
                prev_close = df_full['Close'].iloc[-2]
                pct_change = ((latest_close - prev_close) / prev_close) * 100
                
                color_hex = "#00D395" if pct_change >= 0 else "#FF4C4A"
                arrow = "▲" if pct_change >= 0 else "▼"
                short_name = info.get('shortName', ticker)
                
                gainers, losers, trending = fetch_market_movers()
                news_items = get_news_cached(ticker)
                
                # --- 3-COLUMN LAYOUT ---
                col_left, col_center, col_right = st.columns([1.5, 3.7, 1.4], gap="large")
                
                with col_left:
                    def fmt(val, is_pct=False):
                        if val is None or val == 'N/A': return "--"
                        if is_pct: return f"{val * 100:.2f}%"
                        if isinstance(val, (int, float)):
                            if val >= 1e12: return f"${val/1e12:.2f}T"
                            if val >= 1e9: return f"${val/1e9:.2f}B"
                            if val >= 1e6: return f"${val/1e6:.2f}M"
                            return f"{val:,.2f}"
                        return val

                    st.markdown(f"""<div class="left-static-header"><div style="font-size: 24px; font-weight: 700; color: #F3F5F7;">{ticker}</div><div style="color: #8A919E; font-size: 13px; margin-top: -4px; margin-bottom: 10px;">{short_name}</div><div style="font-size: 30px; font-weight: 700; color: #F3F5F7; margin-bottom: -2px;">${latest_close:,.2f}</div><div style="color: {color_hex}; font-weight: 700; font-size: 14px;">{arrow} {abs(pct_change):.2f}% <span style="color: #8A919E; font-weight: 400; font-size: 12px;">(1d)</span></div></div>""", unsafe_allow_html=True)
                    
                    with st.container(border=False):
                        def get_info_box(label, value, tooltip_text):
                            return f"""<div class="small-info-box"><div class="small-info-label">{label} <span title="{tooltip_text}" style="cursor: help; margin-left: 5px; color: #8A919E;">ⓘ</span></div><div class="small-info-val">{value}</div></div>"""
                        
                        pcr_val = f"{put_call_ratio:.2f}" if put_call_ratio else "N/A"

                        if not is_crypto_or_commodity:
                            marketcap_desc = "The total market value of a company's outstanding shares."
                            vol_desc = "A measure of how much of this asset was traded in the last 24 hours."
                            pe_desc = "Price-to-Earnings ratio based on the past 12 months of actual earnings."
                            pcr_desc = "Options Put/Call Ratio. A ratio > 1 suggests bearish sentiment. A ratio < 1 suggests bullish sentiment."
                            margin_desc = "A ratio of a company's profit divided by its revenue."
                            roe_desc = "Return on Equity is calculated by dividing net income by shareholders' equity."
                            
                            st.markdown(f"""<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
{get_info_box("Market cap", fmt(info.get('marketCap')), marketcap_desc)}
{get_info_box("Volume (24h)", fmt(info.get('volume')), vol_desc)}
{get_info_box("Trailing P/E", fmt(info.get('trailingPE')), pe_desc)}
{get_info_box("Put/Call Ratio", pcr_val, pcr_desc)}
{get_info_box("Profit Margin", fmt(info.get('profitMargins'), True), margin_desc)}
{get_info_box("ROE", fmt(info.get('returnOnEquity'), True), roe_desc)}
</div>""", unsafe_allow_html=True)
                        else:
                            marketcap_desc = "The total market value of a circulating supply."
                            vol_desc = "A measure of how much of this asset was traded in the last 24 hours."
                            supply_desc = "The amount of coins/tokens that are circulating in the market."
                            max_desc = "The maximum amount of coins/tokens that will ever exist."
                            vol_to_mc = (info.get('volume24Hr', 0) / info.get('marketCap', 1)) if info.get('marketCap') else 0
                            vol_mc_desc = "Ratio of 24h volume to market cap. Higher means higher liquidity."
                            
                            st.markdown(f"""<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
{get_info_box("Market cap", fmt(info.get('marketCap')), marketcap_desc)}
{get_info_box("Volume (24h)", fmt(info.get('volume24Hr', info.get('volume'))), vol_desc)}
{get_info_box("Circ. Supply", fmt(info.get('circulatingSupply')), supply_desc)}
{get_info_box("Max Supply", fmt(info.get('maxSupply')), max_desc)}
{get_info_box("Vol / MCap", f"{vol_to_mc:.4f}", vol_mc_desc)}
{get_info_box("Put/Call Ratio", pcr_val, "Options derivatives are rare for this asset class.")}
</div>""", unsafe_allow_html=True)
                        
                        st.markdown("<br>", unsafe_allow_html=True)
                        with st.container(border=True):
                            p_col1, p_col2 = st.columns([2.5, 1.5])
                            with p_col1: st.markdown("<div style='color: #F3F5F7; font-weight: 700; font-size: 14px; margin-top: 5px;'>Price performance</div>", unsafe_allow_html=True)
                            with p_col2: perf_tf = st.selectbox("Performance Timeframe", ["24h", "1m", "1y"], index=0, label_visibility="collapsed", key="perf_tf")
                            
                            if perf_tf == "24h":
                                tf_low, tf_high = df_full['Low'].iloc[-1], df_full['High'].iloc[-1]
                            elif perf_tf == "1m":
                                tf_low, tf_high = df_full['Low'].tail(21).min(), df_full['High'].tail(21).max()
                            else:
                                tf_low = info.get('fiftyTwoWeekLow', df_full['Low'].tail(252).min())
                                tf_high = info.get('fiftyTwoWeekHigh', df_full['High'].tail(252).max())
                            
                            try: pos = max(0, min(100, ((latest_close - tf_low) / (tf_high - tf_low)) * 100)) if tf_high > tf_low else 50
                            except: pos = 50
                                
                            st.markdown(f"""<div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 5px; margin-top: 10px;"><span style="color: #8A919E;">Low <br><strong style="color: #F3F5F7;">${tf_low:,.2f}</strong></span><span style="color: #8A919E; text-align: right;">High <br><strong style="color: #F3F5F7;">${tf_high:,.2f}</strong></span></div><div class="perf-bar-bg"><div class="perf-dot" style="left: calc({pos}% - 5px);"></div></div>""", unsafe_allow_html=True)
                            
                            if not df_max.empty:
                                ath = df_max['High'].max()
                                ath_date = df_max['High'].idxmax()
                                atl = df_max['Low'].min()
                                atl_date = df_max['Low'].idxmin()
                                now = pd.Timestamp.now().tz_localize(None)
                                ath_pct = ((latest_close - ath) / ath) * 100
                                atl_pct = ((latest_close - atl) / atl) * 100
                                
                                st.markdown(f"""<div style="margin-top: 15px; border-top: 1px solid #222531; padding-top: 10px;"><div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;"><div><div style="color: #F3F5F7; font-weight: 700; font-size: 12px;">All-time high</div><div style="color: #8A919E; font-size: 11px;">{ath_date.strftime('%b %d, %Y')}</div></div><div style="text-align: right;"><div style="color: #F3F5F7; font-weight: 700; font-size: 13px;">${ath:,.2f}</div><div style="color: {'#FF4C4A' if ath_pct < 0 else '#00D395'}; font-size: 11px; font-weight: 600;">{ath_pct:.2f}%</div></div></div><div style="display: flex; justify-content: space-between; align-items: center;"><div><div style="color: #F3F5F7; font-weight: 700; font-size: 12px;">All-time low</div><div style="color: #8A919E; font-size: 11px;">{atl_date.strftime('%b %d, %Y')}</div></div><div style="text-align: right;"><div style="color: #F3F5F7; font-weight: 700; font-size: 13px;">${atl:,.2f}</div><div style="color: {'#00D395' if atl_pct > 0 else '#FF4C4A'}; font-size: 11px; font-weight: 600;">+{atl_pct:.2f}%</div></div></div></div>""", unsafe_allow_html=True)
                        
                        st.markdown("<h4 style='color: #F3F5F7; margin-top: 20px; font-size: 15px;'>About</h4>", unsafe_allow_html=True)
                        desc = info.get('longBusinessSummary') or info.get('description')
                        if not desc or desc == 'N/A':
                            if "-" in ticker: 
                                desc = f"{short_name} is a decentralized digital asset and cryptocurrency. It operates on a peer-to-peer network without the need for intermediaries. Its price is largely determined by market supply and demand, macroeconomic factors, network adoption, and broader sentiment within the cryptocurrency ecosystem."
                            elif "=F" in ticker: 
                                desc = f"{short_name} is a globally traded commodity and futures contract. Prices are influenced by geopolitical events, supply chain dynamics, inflation, and global macroeconomic trends."
                            else:
                                desc = "No detailed description available for this asset."
                        
                        if len(desc) > 150:
                            if st.session_state.show_full_about:
                                st.markdown(f"<div style='color: #8A919E; font-size: 12px; line-height: 1.5; margin-bottom: 10px;'>{desc}</div>", unsafe_allow_html=True)
                                if st.button("View less", key="v_less_about"): st.session_state.show_full_about = False; st.rerun()
                            else:
                                st.markdown(f"<div style='color: #8A919E; font-size: 12px; line-height: 1.5; margin-bottom: 10px;'>{desc[:150]}...</div>", unsafe_allow_html=True)
                                if st.button("View more", key="v_more_about"): st.session_state.show_full_about = True; st.rerun()
                        else:
                            st.markdown(f"<div style='color: #8A919E; font-size: 12px; line-height: 1.5;'>{desc}</div>", unsafe_allow_html=True)

                with col_center:
                    st.markdown("<div class='vertical-line'></div>", unsafe_allow_html=True)
                    chart_tab1, chart_tab2, chart_tab3 = st.tabs(["📈 Advanced Charting", "🧪 Strategy Backtester", "🔮 Volatility Surface"])
                    
                    with chart_tab1:
                        ctrl_1, ctrl_2 = st.columns([2, 1])
                        with ctrl_1: timeframe = st.radio("Timeframe", ["1d", "1w", "1mo", "3mo", "6mo", "1y", "5y", "Max"], index=3, horizontal=True, label_visibility="collapsed")
                        with ctrl_2: chart_type = st.radio("Chart Type", ["Line", "Candlestick"], index=0, horizontal=True, label_visibility="collapsed")
                    
                        now = pd.Timestamp.now().tz_localize(None)
                        
                        df_chart_base = df_full.copy()
                        df_chart_base['SMA_20'] = df_chart_base['Close'].rolling(window=20).mean()
                        df_chart_base['SMA_50'] = df_chart_base['Close'].rolling(window=50).mean()
                        df_chart_base['Vol_Color'] = ['#00D395' if c >= o else '#FF4C4A' for c, o in zip(df_chart_base['Close'], df_chart_base['Open'])]
                        delta = df_chart_base['Close'].diff()
                        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                        rs = gain / loss
                        df_chart_base['RSI_14'] = 100 - (100 / (1 + rs))
                        
                        if timeframe == "1d":
                            df_chart = yf.Ticker(ticker).history(period="1d", interval="5m").reset_index()
                            date_col = 'Datetime' if 'Datetime' in df_chart.columns else 'Date'
                            df_chart['Date'] = pd.to_datetime(df_chart[date_col]).dt.tz_localize(None)
                            df_chart['SMA_20'] = df_chart['Close'].rolling(window=20).mean()
                            df_chart['SMA_50'] = df_chart['Close'].rolling(window=50).mean()
                            df_chart['Vol_Color'] = ['#00D395' if c >= o else '#FF4C4A' for c, o in zip(df_chart['Close'], df_chart['Open'])]
                            d_in = df_chart['Close'].diff()
                            g_in = (d_in.where(d_in > 0, 0)).rolling(window=14).mean()
                            l_in = (-d_in.where(d_in < 0, 0)).rolling(window=14).mean()
                            df_chart['RSI_14'] = 100 - (100 / (1 + (g_in / l_in)))
                        elif timeframe == "1w":
                            df_chart = yf.Ticker(ticker).history(period="5d", interval="15m").reset_index()
                            date_col = 'Datetime' if 'Datetime' in df_chart.columns else 'Date'
                            df_chart['Date'] = pd.to_datetime(df_chart[date_col]).dt.tz_localize(None)
                            df_chart['SMA_20'] = df_chart['Close'].rolling(window=20).mean()
                            df_chart['SMA_50'] = df_chart['Close'].rolling(window=50).mean()
                            df_chart['Vol_Color'] = ['#00D395' if c >= o else '#FF4C4A' for c, o in zip(df_chart['Close'], df_chart['Open'])]
                            d_in = df_chart['Close'].diff()
                            g_in = (d_in.where(d_in > 0, 0)).rolling(window=14).mean()
                            l_in = (-d_in.where(d_in < 0, 0)).rolling(window=14).mean()
                            df_chart['RSI_14'] = 100 - (100 / (1 + (g_in / l_in)))
                        else:
                            if timeframe == "1mo": start_date = now - pd.DateOffset(months=1)
                            elif timeframe == "3mo": start_date = now - pd.DateOffset(months=3)
                            elif timeframe == "6mo": start_date = now - pd.DateOffset(months=6)
                            elif timeframe == "1y": start_date = now - pd.DateOffset(years=1)
                            elif timeframe == "5y": start_date = now - pd.DateOffset(years=5)
                            else: start_date = pd.Timestamp('1900-01-01') # Max
                            
                            df_chart = df_chart_base[pd.to_datetime(df_chart_base['Date']).dt.tz_localize(None) >= start_date].copy()

                        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.6, 0.2, 0.2])

                        if chart_type == "Line":
                            fig.add_trace(go.Scatter(x=df_chart['Date'], y=df_chart['Close'], fill='tozeroy', mode='lines', line=dict(color=color_hex, width=2.5), fillcolor=f'rgba({0 if pct_change>=0 else 255}, {211 if pct_change>=0 else 76}, {149 if pct_change>=0 else 74}, 0.1)', name='Price'), row=1, col=1)
                        else:
                            fig.add_trace(go.Candlestick(x=df_chart['Date'], open=df_chart['Open'], high=df_chart['High'], low=df_chart['Low'], close=df_chart['Close'], increasing_line_color='#00D395', decreasing_line_color='#FF4C4A', increasing_fillcolor='#00D395', decreasing_fillcolor='#FF4C4A', name='Price'), row=1, col=1)
                        
                        fig.add_trace(go.Scatter(x=df_chart['Date'], y=df_chart['SMA_20'], line=dict(color='#0052FF', width=1.5), name='20-Period SMA'), row=1, col=1)
                        fig.add_trace(go.Scatter(x=df_chart['Date'], y=df_chart['SMA_50'], line=dict(color='#F5B028', width=1.5), name='50-Period SMA'), row=1, col=1)
                        fig.add_trace(go.Bar(x=df_chart['Date'], y=df_chart['Volume'], marker_color=df_chart['Vol_Color'], name='Volume'), row=2, col=1)
                        fig.add_trace(go.Scatter(x=df_chart['Date'], y=df_chart['RSI_14'], line=dict(color='#A1A7BB', width=1.5), name='14-Period RSI'), row=3, col=1)
                        fig.add_hline(y=70, line_dash="dash", line_color="#FF4C4A", row=3, col=1) 
                        fig.add_hline(y=30, line_dash="dash", line_color="#00D395", row=3, col=1) 
                        
                        fig.update_layout(template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(l=0, r=0, t=10, b=0), height=550, hovermode="x unified", showlegend=False, xaxis_rangeslider_visible=False)
                        
                        y_min = df_chart['Low'].min() * 0.95 if 'Low' in df_chart else df_chart['Close'].min() * 0.95
                        y_max = df_chart['High'].max() * 1.05 if 'High' in df_chart else df_chart['Close'].max() * 1.05
                        fig.update_yaxes(range=[y_min, y_max], row=1, col=1)
                        fig.update_xaxes(showgrid=False, showline=False, zeroline=False, color="#8A919E")
                        fig.update_yaxes(showgrid=True, gridcolor='#222531', side='right', color="#8A919E")
                        
                        st.plotly_chart(fig, key="main_advanced_chart")
                        
                    with chart_tab2:
                        st.markdown("<div style='color: #8A919E; font-size: 14px; margin-bottom: 15px;'>Strategy Backtester Engine</div>", unsafe_allow_html=True)
                        bt_mode = st.radio("Engine Type", ["⚡ Basic SMA Crossover", "🧠 XGBoost Walk-Forward ML"], horizontal=True, label_visibility="collapsed")
                        use_regime = st.toggle("🛡️ Enable SPY 200-Day Regime Filter (Hold cash in bear markets)", value=False)
                        
                        if "Basic" in bt_mode:
                            st.markdown("<div style='color: #8A919E; font-size: 13px; margin-bottom: 10px;'>Running fast 1-Year heuristic backtest.</div>", unsafe_allow_html=True)
                            now = pd.Timestamp.now().tz_localize(None)
                            df_bt = df_full[pd.to_datetime(df_full['Date']).dt.tz_localize(None) >= (now - pd.DateOffset(years=1))].copy()
                            df_bt['Daily_Return'] = df_bt['Close'].pct_change()
                            df_bt['Cumulative_Market'] = (1 + df_bt['Daily_Return'].fillna(0)).cumprod()
                            mark_ret = (df_bt['Cumulative_Market'].iloc[-1] - 1) * 100

                            optimize = st.toggle("🧪 Enable Parameter Optimization (Brute Force)", value=False)
                            best_short, best_long, best_rsi, best_ret = 20, 50, 70, -999.0

                            if optimize:
                                short_smas, long_smas, rsi_threshs = [10, 15, 20, 30], [50, 100, 150, 200], [60, 70, 80]
                                with st.spinner("Testing dozens of parameter combinations..."):
                                    for s in short_smas:
                                        for l in long_smas:
                                            for r in rsi_threshs:
                                                temp_df = df_bt.copy()
                                                temp_df['s_sma'] = temp_df['Close'].rolling(window=s).mean()
                                                temp_df['l_sma'] = temp_df['Close'].rolling(window=l).mean()
                                                temp_df['RSI'] = 100 - (100 / (1 + (temp_df['Close'].diff().where(temp_df['Close'].diff() > 0, 0).rolling(14).mean() / -temp_df['Close'].diff().where(temp_df['Close'].diff() < 0, 0).rolling(14).mean())))
                                                temp_df['Signal'] = 0
                                                temp_df.loc[(temp_df['s_sma'] > temp_df['l_sma']) & (temp_df['RSI'] < r), 'Signal'] = 1
                                                temp_df['Cumulative_Strategy'] = (1 + (temp_df['Signal'].shift(1) * temp_df['Daily_Return']).fillna(0)).cumprod()
                                                
                                                s_ret = (temp_df['Cumulative_Strategy'].iloc[-1] - 1) * 100
                                                if s_ret > best_ret: best_ret, best_short, best_long, best_rsi = s_ret, s, l, r
                                st.markdown(f"<div style='color: #00D395; font-size: 13px; margin-bottom: 10px;'>✅ <b>Optimal Parameters Found:</b> Short SMA ({best_short}), Long SMA ({best_long}), RSI < {best_rsi}</div>", unsafe_allow_html=True)

                            df_bt['Active_Short_SMA'] = df_bt['Close'].rolling(window=best_short).mean()
                            df_bt['Active_Long_SMA'] = df_bt['Close'].rolling(window=best_long).mean()
                            df_bt['RSI'] = 100 - (100 / (1 + (df_bt['Close'].diff().where(df_bt['Close'].diff() > 0, 0).rolling(14).mean() / -df_bt['Close'].diff().where(df_bt['Close'].diff() < 0, 0).rolling(14).mean())))
                            
                            df_bt['Signal'] = 0
                            df_bt.loc[(df_bt['Active_Short_SMA'] > df_bt['Active_Long_SMA']) & (df_bt['RSI'] < best_rsi), 'Signal'] = 1
                            
                            if use_regime:
                                try:
                                    spy_data = get_daily_data_cached("SPY", period="max")
                                    spy_data['SPY_SMA_200'] = spy_data['Close'].rolling(200).mean()
                                    df_bt = pd.merge(df_bt, spy_data[['Date', 'Close', 'SPY_SMA_200']], on='Date', how='left', suffixes=('', '_SPY'))
                                    df_bt['Close_SPY'] = df_bt['Close_SPY'].ffill()
                                    df_bt['SPY_SMA_200'] = df_bt['SPY_SMA_200'].ffill()
                                    df_bt.loc[df_bt['Close_SPY'] < df_bt['SPY_SMA_200'], 'Signal'] = 0
                                except Exception:
                                    st.warning("Could not apply regime filter (SPY data error).")
                            
                            df_bt['Strategy_Return'] = df_bt['Signal'].shift(1) * df_bt['Daily_Return']
                            df_bt['Cumulative_Strategy'] = (1 + df_bt['Strategy_Return'].fillna(0)).cumprod()
                            strat_ret = (df_bt['Cumulative_Strategy'].iloc[-1] - 1) * 100
                            
                            bt_fig = go.Figure()
                            bt_fig.add_trace(go.Scatter(x=df_bt['Date'], y=df_bt['Cumulative_Market'], name="Buy & Hold (Market)", line=dict(color="#8A919E", width=2)))
                            bt_fig.add_trace(go.Scatter(x=df_bt['Date'], y=df_bt['Cumulative_Strategy'], name="AI Quant Strategy", line=dict(color="#0052FF", width=3)))
                            
                            bt_fig.update_layout(template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(l=0, r=0, t=10, b=0), height=450, hovermode="x unified", legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01, bgcolor='rgba(23,25,36,0.8)'), xaxis=dict(showgrid=False, showline=False, color="#8A919E"), yaxis=dict(showgrid=True, gridcolor='#222531', side='right', color="#8A919E"))
                            st.plotly_chart(bt_fig, key="backtest_chart")
                            
                            st.markdown(f"""<div style="display: flex; gap: 20px;"><div style="background-color: #171924; border: 1px solid #222531; padding: 15px; border-radius: 8px; flex: 1;"><div style="color: #8A919E; font-size: 13px;">Strategy Return (1Y)</div><div style="color: {'#00D395' if strat_ret > 0 else '#FF4C4A'}; font-size: 20px; font-weight: bold;">{strat_ret:.2f}%</div></div><div style="background-color: #171924; border: 1px solid #222531; padding: 15px; border-radius: 8px; flex: 1;"><div style="color: #8A919E; font-size: 13px;">Buy & Hold Return (1Y)</div><div style="color: {'#00D395' if mark_ret > 0 else '#FF4C4A'}; font-size: 20px; font-weight: bold;">{mark_ret:.2f}%</div></div></div>""", unsafe_allow_html=True)
                        else:
                            st.markdown("<div style='color: #8A919E; font-size: 13px; margin-bottom: 10px;'>Trains a dynamic XGBoost model using Optuna Bayesian Optimization over a rolling window. This evaluates out-of-sample performance and mimics institutional strategies.</div>", unsafe_allow_html=True)
                            
                            if st.button("🚀 Execute Walk-Forward Backtest", type="primary"):
                                try:
                                    from advanced_backtester import MLQuantBacktester
                                    with st.spinner("🤖 Training XGBoost Walk-Forward Model..."):
                                        start_d = (pd.Timestamp.now() - pd.DateOffset(years=5)).strftime('%Y-%m-%d')
                                        ml_bt = MLQuantBacktester(ticker=ticker, start_date=start_d)
                                        results = ml_bt.run_walk_forward_xgboost(train_window=750, test_window=63, use_regime_filter=use_regime)
                                        
                                        df_res = results['data']
                                        strat_ret = results['Return_Pct']
                                        mark_ret = results['Market_Return_Pct']
                                        
                                        bt_fig = go.Figure()
                                        bt_fig.add_trace(go.Scatter(x=df_res['Date'], y=df_res['Cumulative_Market'], name="Buy & Hold (Market)", line=dict(color="#8A919E", width=2)))
                                        bt_fig.add_trace(go.Scatter(x=df_res['Date'], y=df_res['Cumulative_Strategy'], name="XGBoost ML Strategy", line=dict(color="#0052FF", width=3)))
                                        
                                        rolling_max = df_res['Cumulative_Strategy'].cummax()
                                        drawdown = (df_res['Cumulative_Strategy'] / rolling_max) - 1
                                        bt_fig.add_trace(go.Scatter(x=df_res['Date'], y=drawdown, fill='tozeroy', name="Strategy Drawdown", line=dict(color="#FF4C4A", width=1), fillcolor='rgba(255, 76, 74, 0.3)', yaxis='y2'))
                                        
                                        bt_fig.update_layout(template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(l=0, r=0, t=10, b=0), height=550, hovermode="x unified", legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01, bgcolor='rgba(23,25,36,0.8)'), xaxis=dict(showgrid=False, showline=False, color="#8A919E"), yaxis=dict(title="Cumulative Multiplier", showgrid=True, gridcolor='#222531', side='right', color="#8A919E"), yaxis2=dict(title="Drawdown", overlaying='y', side='left', tickformat='.1%', range=[-1, 0], showgrid=False, color="#FF4C4A"))
                                        st.plotly_chart(bt_fig, key="ml_backtest_chart")
                                        
                                        st.markdown(f"""<div style="display: flex; gap: 20px;"><div style="background-color: #171924; border: 1px solid #222531; padding: 15px; border-radius: 8px; flex: 1;"><div style="color: #8A919E; font-size: 13px;">Strategy Return</div><div style="color: {'#00D395' if strat_ret > 0 else '#FF4C4A'}; font-size: 20px; font-weight: bold;">{strat_ret:.2f}%</div><div style="color: #8A919E; font-size: 11px; margin-top: 4px;">Sharpe: {results['Sharpe_Ratio']:.2f} | Trades: {int(results['Total_Trades'])}</div></div><div style="background-color: #171924; border: 1px solid #222531; padding: 15px; border-radius: 8px; flex: 1;"><div style="color: #8A919E; font-size: 13px;">Buy & Hold Return</div><div style="color: {'#00D395' if mark_ret > 0 else '#FF4C4A'}; font-size: 20px; font-weight: bold;">{mark_ret:.2f}%</div><div style="color: #8A919E; font-size: 11px; margin-top: 4px;">Max Drawdown: {results['Max_Drawdown_Pct']:.2f}%</div></div></div>""", unsafe_allow_html=True)
                                except Exception as e:
                                    st.error(f"Error executing advanced backtester: {e}")
                    
                    with chart_tab3:
                        st.markdown("<div style='color: #8A919E; font-size: 14px; margin-bottom: 15px;'>Options Chain Analysis & Implied Volatility (Smart Money Flow)</div>", unsafe_allow_html=True)
                        if put_call_ratio is None:
                            st.warning("No options data available for this asset (Cryptocurrencies and OTC stocks typically do not have standard options chains).")
                        else:
                            vol_df = get_volatility_surface(ticker)
                            if vol_df is not None and not vol_df.empty:
                                fig_vol = go.Figure()
                                fig_vol.add_trace(go.Scatter3d(x=vol_df['Expiration'], y=vol_df['Strike'], z=vol_df['IV'], mode='markers', marker=dict(size=4, color=vol_df['IV'], colorscale='Viridis', opacity=0.8), name='Call Options IV'))
                                fig_vol.update_layout(template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(l=0, r=0, t=10, b=0), height=450, scene=dict(xaxis_title='Expiration', yaxis_title='Strike Price ($)', zaxis_title='Implied Volatility', xaxis=dict(gridcolor='#222531', backgroundcolor='rgba(0,0,0,0)'), yaxis=dict(gridcolor='#222531', backgroundcolor='rgba(0,0,0,0)'), zaxis=dict(gridcolor='#222531', backgroundcolor='rgba(0,0,0,0)')))
                                st.plotly_chart(fig_vol, key="vol_surface_chart")
                                
                                st.markdown(f"""<div style="display: flex; gap: 20px; margin-top: 15px;"><div style="background-color: #171924; border: 1px solid #222531; padding: 15px; border-radius: 8px; flex: 1;"><div style="color: #8A919E; font-size: 13px;">Overall Put/Call Ratio</div><div style="color: {'#FF4C4A' if put_call_ratio > 1 else '#00D395'}; font-size: 20px; font-weight: bold;">{put_call_ratio:.2f}</div><div style="color: #8A919E; font-size: 11px; margin-top: 4px;">{'Bearish Sentiment (More Puts)' if put_call_ratio > 1 else 'Bullish Sentiment (More Calls)'}</div></div></div>""", unsafe_allow_html=True)
                            else: st.warning("Options chain data exists but lacked sufficient liquidity to map the volatility surface.")

                    st.markdown("<br>", unsafe_allow_html=True)
                    
                    # --- MULTI-AGENT DEBATE SYSTEM ---
                    st.markdown("<h3 style='font-size: 18px; margin-bottom: 15px;'>🤖 Multi-Agent Synthesis</h3>", unsafe_allow_html=True)
                    
                    with st.container(border=True):
                        ml_choice = st.radio("Select ML Engine for Synthesis:", ["XGBoost Walk-Forward ML", "TimesFM Transformer Model"], horizontal=True)
                        
                        if not st.session_state.run_ai:
                            st.markdown("<div style='text-align: center; padding: 20px; color: #8A919E;'><p>AI Synthesis is paused for fast performance.</p></div>", unsafe_allow_html=True)
                            if st.button("🚀 Initiate Multi-Agent Analysis", type="primary"):
                                st.session_state.run_ai = True
                                st.session_state.ml_choice = ml_choice
                                st.rerun()
                        else:
                            if st.session_state.ai_report is None:
                                status_placeholder = st.empty()
                                with status_placeholder.container():
                                    st.info("Step 1: Bull & Bear Agents constructing debate thesis...")
                                    st.session_state.ai_report = agent.analyze_stock(ticker, ml_model_choice=st.session_state.ml_choice)
                                status_placeholder.empty()
                                st.rerun()
                            
                            report = st.session_state.ai_report
                            if isinstance(report, dict) and "pm" in report:
                                pm_text, decision = parse_pm_verdict(report["pm"])
                                date_str = datetime.date.today().strftime('%B %d, %Y')
                                
                                st.markdown(f"<div style='color: #8A919E; font-size: 14px; margin-bottom: 10px;'><strong>The analysis for {ticker} and for date {date_str} is:</strong></div>", unsafe_allow_html=True)
                                
                                if decision == "BUY":
                                    st.markdown("#### <span style='color: #00D395;'>⚖️ Final Verdict: BUY</span>", unsafe_allow_html=True)
                                elif decision == "SELL":
                                    st.markdown("#### <span style='color: #FF4C4A;'>⚖️ Final Verdict: SELL</span>", unsafe_allow_html=True)
                                else:
                                    st.markdown("#### <span style='color: #F5B028;'>⚖️ Final Verdict: HOLD</span>", unsafe_allow_html=True)
                                
                                st.markdown(f"<div style='line-height: 1.6; color: #E0E2E7; font-size: 14px;'>{pm_text}</div>", unsafe_allow_html=True)
                                st.markdown("<hr style='margin: 20px 0 10px 0; border-color: #222531;'>", unsafe_allow_html=True)
                                
                                st.markdown("<div style='color: #8A919E; font-size: 12px; margin-bottom: 10px;'>ANALYST DEBATE LOGS</div>", unsafe_allow_html=True)
                                ai_tab1, ai_tab2 = st.tabs(["🟢 Bull Analyst Thesis", "🔴 Bear Analyst Thesis"])
                                with ai_tab1: st.markdown(f"<div style='line-height: 1.6; color: #E0E2E7; font-size: 13px; padding: 15px; background-color: rgba(0, 211, 149, 0.05); border-radius: 8px;'>{report['bull']}</div>", unsafe_allow_html=True)
                                with ai_tab2: st.markdown(f"<div style='line-height: 1.6; color: #E0E2E7; font-size: 13px; padding: 15px; background-color: rgba(255, 76, 74, 0.05); border-radius: 8px;'>{report['bear']}</div>", unsafe_allow_html=True)
                                
                                with st.expander("📰 View Pre-Processed News Context (Fed to LLM)"):
                                    st.markdown(report.get("news", "No news context extracted."))
                                    
                                md_report = f"""# AI Quantitative Trading Report\n**Asset:** {ticker}\n**Date:** {date_str}\n\n## ⚖️ Final Verdict: {decision}\n\n### Executive Synthesis\n{pm_text}\n\n---\n### 🟢 Bull Analyst Thesis\n{report['bull']}\n\n---\n### 🔴 Bear Analyst Thesis\n{report['bear']}\n\n---\n### 📰 Pre-Processed News Context\n{report.get('news', 'No recent news context.')}\n"""
                                st.download_button(label="📄 Download Full AI Report", data=md_report, file_name=f"{ticker}_AI_Report_{date_str.replace(' ', '_').replace(',', '')}.md", mime="text/markdown")
                            else:
                                st.error("Error generating Multi-Agent Debate. Ensure Ollama is running.")

                # ==========================================
                # RIGHT COLUMN: MARKET MOVERS & TIGHT VIEW
                # ==========================================
                with col_right:
                    st.markdown("<div class='vertical-line'></div>", unsafe_allow_html=True)
                    
                    macro_data = get_macro_data()
                    if macro_data:
                        st.markdown("<div class='movers-header' style='margin-top:0;'>Macro Environment</div>", unsafe_allow_html=True)
                        spy_color = "#00D395" if macro_data['SP500']['change'] >= 0 else "#FF4C4A"
                        tnx_color = "#00D395" if macro_data['TNX']['change'] >= 0 else "#FF4C4A"
                        
                        st.markdown(f"""
                        <div style="background-color: #171924; border: 1px solid #222531; border-radius: 8px; padding: 10px; margin-bottom: 15px;">
                            <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                                <span style="color: #F3F5F7; font-size: 12px; font-weight: 600;">S&P 500 (SPY)</span>
                                <span style="color: {spy_color}; font-size: 12px; font-weight: 700;">{macro_data['SP500']['price']:.2f} ({'+' if macro_data['SP500']['change']>=0 else ''}{macro_data['SP500']['change']:.2f}%)</span>
                            </div>
                            <div style="display: flex; justify-content: space-between;">
                                <span style="color: #F3F5F7; font-size: 12px; font-weight: 600;">10Y Treasury</span>
                                <span style="color: {tnx_color}; font-size: 12px; font-weight: 700;">{macro_data['TNX']['price']:.3f}% ({'+' if macro_data['TNX']['change']>=0 else ''}{macro_data['TNX']['change']:.2f}%)</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    if not is_crypto_or_commodity:
                        earnings_date = get_upcoming_earnings(ticker)
                        if earnings_date:
                            st.markdown("<div class='movers-header' style='margin-top: 0;'>Earnings Calendar</div>", unsafe_allow_html=True)
                            st.markdown(f"""
                            <div style="background-color: #171924; border: 1px solid #222531; border-radius: 8px; padding: 10px; margin-bottom: 15px; text-align: center;">
                                <div style="color: #8A919E; font-size: 11px; text-transform: uppercase;">Upcoming Report Date</div>
                                <div style="color: #F5B028; font-size: 13px; font-weight: 700; margin-top: 2px;">{earnings_date}</div>
                            </div>
                            """, unsafe_allow_html=True)
                    else:
                        st.markdown("<div class='movers-header' style='margin-top: 0;'>Asset Characteristics</div>", unsafe_allow_html=True)
                        st.markdown(f"""
                        <div style="background-color: rgba(0, 211, 149, 0.05); border: 1px solid rgba(0, 211, 149, 0.2); border-radius: 8px; padding: 10px; margin-bottom: 15px;">
                            <div style="color: #8A919E; font-size: 11px; margin-bottom: 2px;">Trading Hours</div>
                            <div style="color: #00D395; font-size: 12px; font-weight: 600; margin-bottom: 8px;">24/7 Global Market</div>
                            <div style="color: #8A919E; font-size: 11px; margin-bottom: 2px;">Macro Dependency</div>
                            <div style="color: #F3F5F7; font-size: 11px; line-height: 1.4;">Highly sensitive to central bank liquidity & inflation data.</div>
                        </div>
                        """, unsafe_allow_html=True)

                    def render_movers_list(title, items, prefix):
                        if not items: return
                        st.markdown(f"<div class='movers-header' style='margin-top:0;'>{title}</div>", unsafe_allow_html=True)
                        for idx, item in enumerate(items):
                            i_color = "#00D395" if item['change'] >= 0 else "#FF4C4A"
                            i_arrow = "+" if item['change'] >= 0 else ""
                            
                            spark = go.Figure(go.Scatter(y=item['history'], mode='lines', line=dict(color=i_color, width=1.5)))
                            s_min, s_max = min(item['history']) * 0.98, max(item['history']) * 1.02
                            spark.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(l=0, r=0, t=0, b=0), height=20, width=50, xaxis=dict(visible=False), yaxis=dict(visible=False, range=[s_min, s_max]), showlegend=False, hovermode=False)
                            
                            mc1, mc2, mc3 = st.columns([1.5, 1, 1.2])
                            with mc1: 
                                if st.button(item['ticker'], key=f"btn_{prefix}_{idx}_{item['ticker']}", type="tertiary"):
                                    st.session_state.current_ticker = item['ticker']
                                    st.rerun()
                                st.markdown(f"<div style='color: #8A919E; font-size: 10px; margin-top: -12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;'>{item['name']}</div>", unsafe_allow_html=True)
                            with mc2: st.plotly_chart(spark, config={'displayModeBar': False}, key=f"spark_{prefix}_{idx}_{item['ticker']}")
                            with mc3: st.markdown(f"<div style='text-align: right;'><div style='font-weight: 700; color: #F3F5F7; font-size: 12px;'>{item['price']:.2f}</div><div style='color: {i_color}; font-size: 10px; font-weight: 600;'>{i_arrow}{item['change']:.2f}%</div></div>", unsafe_allow_html=True)
                            st.markdown("<div style='border-bottom: 1px dashed #222531; margin: 4px 0 8px 0;'></div>", unsafe_allow_html=True)

                    with st.container(border=True):
                        render_movers_list("Trending", trending, "trending")
                        render_movers_list("Top Gainers", gainers, "gainers")
                        render_movers_list("Top Losers", losers, "losers")
                    
                    st.markdown("<br><div class='movers-header' style='margin-top:0px;'>Relevant News</div>", unsafe_allow_html=True)
                    if news_items:
                        for n in news_items[:4]:  # Show only top 4 in sidebar to save space
                            title, link, publisher = n.get('title', 'No Title'), n.get('url', '#'), n.get('source', 'Unknown Source')
                            st.markdown(f"<div style='margin-bottom: 10px;'><a href='{link}' target='_blank' class='news-link' style='font-size: 12px;'>{title}</a><div class='news-meta' style='font-size: 10px;'>{publisher}</div></div>", unsafe_allow_html=True)
                        
                        if st.button("View More News ➔"):
                            st.session_state.nav_tab = "News"
                            st.rerun()
                    else: 
                        st.caption("No recent news found for this asset.")

        except Exception as e:
            st.error(f"⚠️ App Execution Error: {e}")

# ==========================================
# VIEW 2: NEWS HUB
# ==========================================
elif st.session_state.nav_tab == "News":
    st.markdown(f"<h2 style='color: #F3F5F7; margin-top: 10px;'>📰 News Hub: {ticker} & Markets</h2>", unsafe_allow_html=True)
    
    col_news_l, col_news_r = st.columns([2, 1.5], gap="large")
    
    with col_news_l:
        st.markdown(f"<h4 style='color: #8A919E; font-size: 16px; margin-bottom: 20px; border-bottom: 1px solid #222531; padding-bottom: 10px;'>Latest Headlines for {ticker}</h4>", unsafe_allow_html=True)
        asset_news = get_news_cached(ticker)
        
        if asset_news:
            for n in asset_news:
                title, link, publisher, body, image_url = n.get('title', 'No Title'), n.get('url', '#'), n.get('source', ''), n.get('body', ''), n.get('image', '')
                
                img_html = f"<img src='{image_url}' style='width: 100px; height: 100px; object-fit: cover; border-radius: 8px;' onerror=\"this.style.display='none'\"/>" if image_url else ""
                
                st.markdown(f"""
                <div style='display: flex; gap: 15px; margin-bottom: 25px; background: #171924; padding: 15px; border-radius: 12px; border: 1px solid #222531;'>
                    {img_html}
                    <div>
                        <a href='{link}' target='_blank' style='color: #F3F5F7; text-decoration: none; font-weight: 700; font-size: 16px; display: block; margin-bottom: 5px;'>{title}</a>
                        <div style='color: #8A919E; font-size: 13px; line-height: 1.5; margin-bottom: 8px;'>{body[:150]}...</div>
                        <div style='color: #0052FF; font-size: 11px; font-weight: 600; text-transform: uppercase;'>{publisher}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info(f"No recent news found for {ticker}.")

    with col_news_r:
        st.markdown("<h4 style='color: #8A919E; font-size: 16px; margin-bottom: 20px; border-bottom: 1px solid #222531; padding-bottom: 10px;'>Top Financial News</h4>", unsafe_allow_html=True)
        gen_news = get_general_news_cached()
        
        if gen_news:
            for n in gen_news:
                title, link, publisher, image_url = n.get('title', 'No Title'), n.get('url', '#'), n.get('source', ''), n.get('image', '')
                
                img_html = f"<img src='{image_url}' style='width: 60px; height: 60px; object-fit: cover; border-radius: 6px;' onerror=\"this.style.display='none'\"/>" if image_url else ""
                
                st.markdown(f"""
                <div style='display: flex; gap: 10px; margin-bottom: 15px; align-items: center;'>
                    {img_html}
                    <div>
                        <a href='{link}' target='_blank' style='color: #F3F5F7; text-decoration: none; font-weight: 600; font-size: 13px; display: block; margin-bottom: 3px; line-height: 1.4;'>{title}</a>
                        <div style='color: #8A919E; font-size: 10px; text-transform: uppercase;'>{publisher}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.caption("No broader market news found.")

# ==========================================
# VIEW 3: MY PORTFOLIO DASHBOARD
# ==========================================
elif st.session_state.nav_tab == "My Portfolio":
    st.markdown("<h2 style='color: #F3F5F7; margin-top: 10px; margin-bottom: 20px;'>💼 Portfolio Overview</h2>", unsafe_allow_html=True)
    port_data = fetch_portfolio_prices(list(st.session_state.portfolio.keys()))
    
    total_value, total_prev_value, asset_names, asset_values, portfolio_html = 0.0, 0.0, [], [], ""
    for asset, qty in st.session_state.portfolio.items():
        if asset in port_data:
            price, prev_price = port_data[asset]['price'], port_data[asset]['prev_price']
            val, prev_val = price * qty, prev_price * qty
            total_value += val; total_prev_value += prev_val
            asset_names.append(asset); asset_values.append(val)
            pct_change = ((price - prev_price) / prev_price) * 100
            portfolio_html += f"<div class='portfolio-item'><div><div style='font-weight: 700; font-size: 16px; color: #F3F5F7;'>{asset}</div><div style='color: #8A919E; font-size: 13px;'>{qty:g} shares @ ${price:,.2f}</div></div><div style='text-align: right;'><div style='font-weight: 700; font-size: 16px; color: #F3F5F7;'>${val:,.2f}</div><div style='color: {'#00D395' if pct_change>=0 else '#FF4C4A'}; font-size: 13px; font-weight: 600;'>{'▲' if pct_change>=0 else '▼'} {abs(pct_change):.2f}%</div></div></div>"
            
    tot_pct_change = ((total_value - total_prev_value) / total_prev_value) * 100 if total_prev_value > 0 else 0
    var_pct = calculate_portfolio_var(st.session_state.portfolio)
    
    # Handle NaN values for VaR cleanly
    if pd.isna(var_pct) or np.isnan(var_pct):
        var_dollar_str = "N/A"
    else:
        var_dollar = total_value * abs(var_pct / 100)
        var_dollar_str = f"-${var_dollar:,.2f}"
    
    port_col1, port_col2 = st.columns([1.5, 1], gap="large")

    with port_col1:
        st.markdown(f"""
        <div style='background-color: #171924; padding: 30px; border-radius: 12px; border: 1px solid #222531; margin-bottom: 25px;'>
            <div style='display: flex; justify-content: space-between; align-items: flex-start;'>
                <div>
                    <div style='color: #8A919E; font-size: 16px; margin-bottom: 5px;'>Total Balance</div>
                    <div style='color: #F3F5F7; font-size: 48px; font-weight: 700; margin-bottom: 5px;'>${total_value:,.2f}</div>
                    <div style='color: {'#00D395' if tot_pct_change>=0 else '#FF4C4A'}; font-weight: 600; font-size: 18px;'>
                        {'▲' if tot_pct_change>=0 else '▼'} ${abs(total_value - total_prev_value):,.2f} ({abs(tot_pct_change):.2f}%) 
                        <span style='color: #8A919E; font-size: 14px; font-weight: 400;'>Today</span>
                    </div>
                </div>
                <div style='text-align: right; background-color: rgba(255, 76, 74, 0.1); padding: 10px 15px; border-radius: 8px; border: 1px solid rgba(255, 76, 74, 0.3);'>
                    <div style='color: #8A919E; font-size: 12px; margin-bottom: 3px;' title='The maximum expected loss in a single day with 95% confidence.'>95% Daily VaR ⓘ</div>
                    <div style='color: #FF4C4A; font-size: 18px; font-weight: 700;'>{var_dollar_str}</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        if asset_values:
            fig_pie = go.Figure(data=[go.Pie(labels=asset_names, values=asset_values, hole=.6, marker=dict(colors=['#0052FF', '#00D395', '#F5B028', '#FF4C4A', '#A1A7BB']))])
            fig_pie.update_layout(template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(l=0, r=0, t=30, b=0), height=300, title=dict(text="Asset Allocation", font=dict(color="#F3F5F7", size=18)))
            st.plotly_chart(fig_pie, key="portfolio_pie")

            corr_matrix = fetch_correlation_matrix(list(st.session_state.portfolio.keys()))
            if corr_matrix is not None:
                st.markdown("<h4 style='color: #F3F5F7; margin-top: 20px; font-size: 18px;'>Portfolio Correlation Heatmap</h4>", unsafe_allow_html=True)
                st.markdown("<p style='color: #8A919E; font-size: 13px; margin-top: -5px;'>Values near 1.0 indicate assets move perfectly together. Values near 0 indicate diversification.</p>", unsafe_allow_html=True)
                
                fig_corr = go.Figure(data=go.Heatmap(
                    z=corr_matrix.values, x=corr_matrix.columns, y=corr_matrix.index,
                    colorscale='RdBu_r', zmin=-1, zmax=1, text=np.round(corr_matrix.values, 2), texttemplate="%{text}", hoverinfo="text"
                ))
                fig_corr.update_layout(template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(l=0, r=0, t=10, b=0), height=300, xaxis=dict(showgrid=False), yaxis=dict(showgrid=False, autorange='reversed'))
                st.plotly_chart(fig_corr, key="portfolio_corr")

    with port_col2:
        st.markdown("<h4 style='color: #8A919E; font-size: 14px; margin-bottom: 15px;'>CURRENT HOLDINGS</h4>", unsafe_allow_html=True)
        if not st.session_state.portfolio: st.caption("Your portfolio is empty.")
        else:
            with st.container(height=350, border=False): st.markdown(portfolio_html, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("<div style='color: #F3F5F7; font-size: 16px; margin-bottom: 10px; font-weight: 700;'>⚙️ Manage Portfolio</div>", unsafe_allow_html=True)
            new_ticker = st.text_input("Asset Ticker", key="port_tick_add", placeholder="e.g., MSFT, BTC-USD").upper()
            new_qty = st.number_input("Quantity", min_value=0.0001, step=0.01, value=1.0)
            
            if st.button("Add / Update Position", type="primary"):
                if new_ticker: st.session_state.portfolio[new_ticker] = new_qty; st.rerun()
            
            st.markdown("<hr style='margin: 15px 0; border-color: #222531;'>", unsafe_allow_html=True)
            if st.session_state.portfolio:
                remove_ticker = st.selectbox("Select Asset to Remove", options=list(st.session_state.portfolio.keys()), label_visibility="collapsed")
                if st.button("Remove Asset"): del st.session_state.portfolio[remove_ticker]; st.rerun()

# ==========================================
# VIEW 4: QUANT Academy (EDUCATION)
# ==========================================
elif st.session_state.nav_tab == "Quant Academy":
    st.markdown("""
    <div style="background-color: #171924; border: 1px solid #222531; border-radius: 12px; padding: 30px; margin-bottom: 25px;">
        <h2 style="color: #F3F5F7; margin-top: 0px; margin-bottom: 10px;">📚 Quant Academy</h2>
        <p style="color: #8A919E; font-size: 15px; margin-bottom: 0px;">Master the technical indicators, risk metrics, and machine learning models powering the AI Trading Terminal.</p>
    </div>
    """, unsafe_allow_html=True)

    edu_col1, edu_col2 = st.columns(2, gap="large")
    
    with edu_col1:
        st.markdown("<h3 style='color: #F3F5F7; margin-bottom: 15px; font-size: 18px;'>📊 Technical & Sentiment Indicators</h3>", unsafe_allow_html=True)
        with st.expander("RSI (Relative Strength Index)"):
            st.markdown("**What it is:** A momentum oscillator that measures the speed and magnitude of recent price changes. It ranges from 0 to 100.\n* **Overbought (>70):** Suggests the asset has risen too fast and may be due for a pullback.\n* **Oversold (<30):** Suggests the asset has fallen too far and may be undervalued.\n* *Pro Tip:* In strong bull markets, RSI can stay 'overbought' for weeks.")
        with st.expander("MACD (Moving Average Convergence Divergence)"):
            st.markdown("**What it is:** A trend-following momentum indicator that shows the relationship between two moving averages.\n* **Bullish Signal:** When the MACD line crosses *above* the signal line.\n* **Bearish Signal:** When the MACD line crosses *below* the signal line.")
        with st.expander("SMA (Simple Moving Average)"):
            st.markdown("**What it is:** The average price of an asset over a specific number of days.\n* **20-Day SMA:** A short-term trend line.\n* **50-Day SMA:** A medium-term trend line.\n* **200-Day SMA:** The ultimate macro-trend line used to determine if an asset is in a fundamental Bull or Bear market.")

    with edu_col2:
        st.markdown("<h3 style='color: #F3F5F7; margin-bottom: 15px; font-size: 18px;'>🧠 Risk Metrics & Machine Learning</h3>", unsafe_allow_html=True)
        with st.expander("Value at Risk (VaR)"):
            st.markdown("**What it is:** A risk management metric used by major banks to quantify the extent of possible financial losses within a portfolio over a specific timeframe.\n* **95% Daily VaR:** Means there is a 95% statistical confidence that your portfolio will *not* lose more than this dollar amount in a single trading day.")
        with st.expander("Sharpe Ratio"):
            st.markdown("**What it is:** The golden standard of risk-adjusted return. It measures how much excess return you receive for the extra volatility you endure.\n* **Sharpe < 1.0:** Sub-optimal.\n* **Sharpe > 1.0:** Good.\n* **Sharpe > 2.0:** Excellent (Very rare in live trading).")
        with st.expander("XGBoost Walk-Forward Backtesting"):
            st.markdown("**What it is:** A professional methodology for testing Machine Learning algorithms to prevent 'Curve Fitting' (overfitting to past data).\n1.  **Train:** The AI looks at 750 days of data and optimizes its parameters.\n2.  **Walk:** The AI is forced to predict the next 63 days of 'blind' future data.\n3.  **Repeat:** The window shifts forward.")

# ==========================================
# FOOTER: ABOUT & CONTACT
# ==========================================
st.markdown("<br><br>", unsafe_allow_html=True)
st.markdown("<hr style='border-color: #222531; margin-bottom: 30px;'>", unsafe_allow_html=True)

f_col1, f_col2, f_col3 = st.columns([2, 1, 1], gap="large")

with f_col1:
    st.markdown("<h4 style='color: #F3F5F7; font-size: 15px; margin-bottom: 10px;'>About Hermes Quant</h4>", unsafe_allow_html=True)
    st.markdown("<div style='color: #8A919E; font-size: 13px; line-height: 1.6;'>Hermes Quant is an institutional-grade, AI-driven quantitative trading terminal. It fuses state-of-the-art machine learning (XGBoost, TimesFM) with dynamic multi-agent LLM debates and live RAG news pipelines to deliver actionable market intelligence and rigorous risk management.</div>", unsafe_allow_html=True)

with f_col2:
    st.markdown("<h4 style='color: #F3F5F7; font-size: 15px; margin-bottom: 10px;'>Contact</h4>", unsafe_allow_html=True)
    st.markdown("""
    <div style='color: #8A919E; font-size: 13px; line-height: 1.8;'>
        📧 <a href='mailto:danialdatak@gmail.com' style='color: #0052FF; text-decoration: none;'>danialdatak@gmail.com</a><br>
    </div>
    """, unsafe_allow_html=True)

with f_col3:
    st.markdown("<h4 style='color: #F3F5F7; font-size: 15px; margin-bottom: 10px;'>Connect</h4>", unsafe_allow_html=True)
    st.markdown("""
    <div style='color: #8A919E; font-size: 13px; line-height: 1.8;'>
        🔗 <a href='https://www.linkedin.com/in/daniel-kiani/' target='_blank' style='color: #0052FF; text-decoration: none;'>LinkedIn Profile</a><br>
        💻 <a href='https://github.com/danielkiani' target='_blank' style='color: #0052FF; text-decoration: none;'>GitHub Repository</a>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<div style='text-align: center; color: #8A919E; font-size: 11px; margin-top: 40px; margin-bottom: 20px;'>© 2026 Hermes Quant. All rights reserved.</div>", unsafe_allow_html=True)