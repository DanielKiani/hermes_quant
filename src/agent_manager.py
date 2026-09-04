import json
import requests
import pandas as pd
import yfinance as yf
import sys
import os
from concurrent.futures import ThreadPoolExecutor

# Ensure we can import the backtester locally
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

class TradingAgentManager:
    def __init__(self, host=None, model="llama3"):
        if host is None:
            # Read from the environment variable (configured in the Canvas docker-compose.yml),
            # falling back to localhost if running natively.
            host = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.host = host
        self.model = model
        self.api_url = f"{self.host}/api/generate"

    def _get_basic_context(self, ticker):
        """Fetches basic price context to ground the LLM."""
        try:
            tick = yf.Ticker(ticker)
            hist = tick.history(period="1mo")
            if hist.empty:
                return "No recent price data available."
            current = hist['Close'].iloc[-1]
            month_ago = hist['Close'].iloc[0]
            pct_change = ((current - month_ago) / month_ago) * 100
            
            info = tick.get_info() or {}
            quote_type = str(info.get("quoteType") or "UNKNOWN").upper()
            is_crypto = quote_type == "CRYPTOCURRENCY" or ticker.endswith("-USD")
            asset_type = "Cryptocurrency" if is_crypto else quote_type.replace("_", " ").title()
            fundamental_warning = ""
            if is_crypto:
                fundamental_warning = " NOTE: Traditional corporate valuation metrics such as earnings and P/E do not apply. Use only the supplied price, macro, network, and headline evidence."
                
            return f"Asset Type: {asset_type}. Current Price: ${current:.2f}. 1-Month Change: {pct_change:.2f}%. {fundamental_warning}"
        except Exception:
            return "Context unavailable."

    def _get_ml_context(self, ticker, ml_model_choice):
        """Runs either XGBoost inference or TimesFM Transformer for the LLM Context."""
        if "XGBoost" in ml_model_choice:
            try:
                import xgboost as xgb
                from advanced_backtester import MLQuantBacktester
                start_d = (pd.Timestamp.now() - pd.DateOffset(years=3)).strftime('%Y-%m-%d')
                
                try: bt = MLQuantBacktester(ticker=ticker, start_date=start_d)
                except TypeError: bt = MLQuantBacktester(ticker=ticker, start_date=start_d, commission=0.001)
                
                if hasattr(bt, 'predict_today'):
                    ml_data = bt.predict_today()
                    prob = ml_data['probability_up'] * 100
                    rsi = ml_data.get('rsi', 50.0)
                    vol = ml_data.get('volatility', 0.0) * 100 
                else:
                    df, feature_cols = bt._engineer_features()
                    train_df = df.dropna(subset=['Target'])
                    latest_features = df.iloc[-1:][feature_cols]
                    
                    # RUN A FAST OPTIMIZATION INSTEAD OF HARDCODING
                    # We run 10 trials to find the best parameters for the current regime in seconds
                    best_params = bt._optimize_hyperparameters(train_df, feature_cols, n_trials=10)
                    
                    model = xgb.XGBClassifier(**best_params, random_state=42, eval_metric='logloss')
                    model.fit(train_df[feature_cols], train_df['Target'])
                    prob = model.predict_proba(latest_features)[0][1] * 100
                    rsi = latest_features['RSI_14'].values[0] if 'RSI_14' in latest_features else 50.0
                    vol = latest_features['Vol_20d'].values[0] * 100 if 'Vol_20d' in latest_features else 0.0
                
                method = ml_data.get('method', 'tabular classifier')
                validation_loss = ml_data.get('validation_log_loss')
                validation_note = f" Purged validation log loss: {validation_loss:.3f}." if validation_loss is not None else ""
                context = f"Validation-selected tabular model ({method}) probability of a positive 5-day return: {prob:.1f}%. Current RSI: {rsi:.1f}. Recent daily volatility: {vol:.2f}%.{validation_note}"
                rules = (
                    f"1. The ML Engine Probability is your directional anchor (Baseline: >52% leans BUY, <48% leans SELL).\n"
                    f"2. You may OVERRIDE the ML baseline ONLY IF the qualitative arguments and recent news present severe, asymmetric risk/reward not captured by historical quantitative data."
                )
                return context, rules
            except Exception as e:
                return f"XGBoost Quantitative Model unavailable ({e}).", "No ML guidelines available."
        else:
            try:
                from predictor import TimesFMPredictor
                from data_loader import get_closing_prices
                predictor = TimesFMPredictor(context_len=1024, horizon_len=5)
                prices = get_closing_prices(ticker)
                curr_price = prices[-1]
                forecast = predictor(prices)
                med, p10, p90 = forecast['median'][-1], forecast['p10'][-1], forecast['p90'][-1]
                
                context = f"TimesFM Transformer forecasts a 5-day median price of ${med:.2f} (Current: ${curr_price:.2f}). Bearish Bound (P10): ${p10:.2f}. Bullish Bound (P90): ${p90:.2f}."
                rules = (
                    f"1. The TimesFM Transformer prediction is your anchor. If the median (${med:.2f}) is strictly higher than the current price (${curr_price:.2f}), lean BUY.\n"
                    f"2. If the median is below the current price, lean SELL.\n"
                    f"3. You may OVERRIDE this baseline ONLY IF the qualitative arguments and recent news present severe risk/reward not captured by the forecast."
                )
                return context, rules
            except Exception as e:
                return f"TimesFM Transformer unavailable ({e}). Make sure your Python environment has the timesfm library installed.", "No ML guidelines available."

    def _get_news_context(self, ticker):
        """Builds a deterministic headline index without adding generated claims."""
        try:
            from src.backend.services import fetch_news

            raw_news = fetch_news(ticker, limit=8).get("items", [])
            if not raw_news:
                return "No recent news available."
            return "\n".join(
                f"- Headline {index}: {item.get('title', 'Untitled')} "
                f"(Publisher: {item.get('publisher', 'Unknown')})"
                for index, item in enumerate(raw_news, start=1)
            )
        except Exception as e:
            return f"News Context unavailable ({e})."

    def _query_ollama(self, prompt, role_description):
        """Sends a prompt to the local Ollama model."""
        payload = {"model": self.model, "prompt": prompt, "system": role_description, "stream": False}
        try:
            response = requests.post(self.api_url, json=payload, timeout=45)
            response.raise_for_status()
            return response.json().get("response", "Error: No response text.")
        except requests.exceptions.RequestException as e:
            return f"Ollama Connection Error: Ensure Ollama is running locally. ({e})"

    def analyze_stock(self, ticker, ml_model_choice="XGBoost"):
        """Orchestrates the multi-agent debate with ML and News injection."""
        context = self._get_basic_context(ticker)
        ml_context, ml_rules = self._get_ml_context(ticker, ml_model_choice)
        news_context = self._get_news_context(ticker)
        
        # --- BULL AGENT ---
        bull_sys = (
            "You are a long-biased research analyst. Use only facts explicitly present "
            "in the supplied market context and headline index. Never invent valuation "
            "multiples, financial metrics, products, targets, dates, or catalysts. Label "
            "interpretation as inference and say when evidence is insufficient."
        )
        bull_prompt = f"Asset: {ticker}\nMarket Data Context: {context}\n\nRECENT NEWS TO CONSIDER:\n{news_context}\n\nTask: Formulate one concise paragraph containing the strongest evidence-supported bullish thesis. Do not add facts that are absent from the inputs."
        # --- BEAR AGENT ---
        bear_sys = (
            "You are a skeptical risk analyst. Use only facts explicitly present in the "
            "supplied market context and headline index. Never invent valuation multiples, "
            "financial metrics, products, targets, dates, or catalysts. Label interpretation "
            "as inference and say when evidence is insufficient."
        )
        bear_prompt = f"Asset: {ticker}\nMarket Data Context: {context}\n\nRECENT NEWS TO CONSIDER:\n{news_context}\n\nTask: Formulate a concise bearish thesis using the strongest evidence-grounded risk case without inventing facts."
        # Bull and bear roles are independent. Run them concurrently, then pass both
        # completed arguments to the judge so the committee remains causally ordered.
        with ThreadPoolExecutor(max_workers=2) as executor:
            bull_future = executor.submit(self._query_ollama, bull_prompt, bull_sys)
            bear_future = executor.submit(self._query_ollama, bear_prompt, bear_sys)
            bull_thesis = bull_future.result()
            bear_thesis = bear_future.result()

        # --- PORTFOLIO MANAGER (JUDGE) ---
        pm_sys = (
            "You are a research synthesis agent, not an investment adviser. Use only the "
            "supplied inputs. Do not introduce new facts or figures. Follow the quantitative "
            "baseline unless you explicitly cite a supplied headline or thesis statement as "
            "the reason for an override."
        )
        pm_prompt = (
            f"Evaluate {ticker} for capital allocation.\n\n"
            f"QUANTITATIVE ML ENGINE ({ml_model_choice}):\n{ml_context}\n\n"
            f"PRE-PROCESSED NEWS HEADLINES:\n{news_context}\n\n"
            f"LONG ANALYST (BULL):\n{bull_thesis}\n\n"
            f"SHORT ANALYST (BEAR):\n{bear_thesis}\n\n"
            f"DECISION FRAMEWORK:\n{ml_rules}\n\n"
            f"FORMATTING RULES:\n"
            f"You must output your response in the exact structure below. Do not add conversational text outside of this structure.\n\n"
            f"If the final decision differs from the ML baseline, write OVERRIDE: YES and cite the exact supplied evidence. Otherwise write OVERRIDE: NO. Never claim to follow the baseline while returning a different decision.\n"
            f"OVERRIDE: [YES or NO, followed by the supplied reason]\n"
            f"SYNTHESIS: [Write a 3-4 sentence paragraph justifying your decision. Explicitly state if you are following or overriding the ML engine and why based on the news/theses.]\n"
            f"FINAL DECISION: [Must be exactly BUY, SELL, or HOLD]"
        )
        pm_response = self._query_ollama(pm_prompt, pm_sys)

        return {
            "asset_context": context,
            "quant": {
                "requested_model": ml_model_choice,
                "summary": ml_context,
                "decision_framework": ml_rules,
            },
            "bull": bull_thesis,
            "bear": bear_thesis,
            "pm": pm_response,
            "news": news_context,
        }
