import pandas as pd
import numpy as np
from predictor import TimesFMPredictor
from data_loader import download_daily_data
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
import time
import re
import os

class AgentBacktester:
    def __init__(self):
        print("Initializing Advanced Backtesting Engine...")
        self.predictor = TimesFMPredictor(context_len=1024, horizon_len=1)
        
        # Pull the Ollama base URL dynamically from the environment variables defined in the Canvas docker-compose.yml
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.llm = ChatOllama(model="llama3", base_url=base_url, temperature=0.0) # Zero temp for strict consistency
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a quantitative trading algorithm. 
            You must evaluate the technical forecast and momentum indicators.
            
            You must respond ONLY with a structured output in this EXACT format:
            DECISION: [BUY, SELL, or HOLD]
            CONFIDENCE: [A number between 0 and 100]
            
            Example:
            DECISION: BUY
            CONFIDENCE: 85"""),
            
            ("user", """
            Current Price: ${current_price:.2f}
            
            INDICATORS:
            20-Day SMA: ${sma:.2f}
            14-Day RSI: {rsi:.2f}
            MACD: {macd:.2f}
            
            AI FORECAST (Next Day):
            Predicted Median: ${predicted_price:.2f}
            Bearish Bound (P10): ${p10:.2f}
            Bullish Bound (P90): ${p90:.2f}
            
            OUTPUT:""")
        ])
        
    def run_backtest(self, ticker: str, days_to_test: int = 10, initial_capital: float = 10000.0):
        print(f"\n========== STARTING {days_to_test}-DAY BACKTEST FOR {ticker} ==========")
        print(f"Initial Capital: ${initial_capital:,.2f}")
        
        df = download_daily_data(ticker, period="1y")
        
        df['SMA_20'] = df['Close'].rolling(window=20).mean()
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI_14'] = 100 - (100 / (1 + rs))
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        
        df = df.dropna().reset_index(drop=True)
        close_prices = df['Close'].values
        dates = df['Date'].values
        
        if len(close_prices) < days_to_test + 10:
            print("Not enough data to backtest.")
            return

        capital = initial_capital
        win_count = 0
        loss_count = 0
        
        for i in range(days_to_test, 0, -1):
            target_idx = len(close_prices) - i - 1
            
            historical_slice = close_prices[:target_idx + 1]
            current_date = dates[target_idx]
            current_price = historical_slice[-1]
            actual_next_price = close_prices[target_idx + 1]
            
            # 1. Run TimesFM Forecast
            forecast = self.predictor(historical_slice)
            
            # 2. Ask Llama-3 for a Risk-Managed Decision
            chain = self.prompt | self.llm
            response = chain.invoke({
                "current_price": current_price,
                "sma": df.loc[target_idx, 'SMA_20'],
                "rsi": df.loc[target_idx, 'RSI_14'],
                "macd": df.loc[target_idx, 'MACD'],
                "predicted_price": forecast['median'][-1],
                "p10": forecast['p10'][-1],
                "p90": forecast['p90'][-1]
            })
            
            output = response.content.strip()
            
            decision = "HOLD"
            confidence = 0.0
            
            try:
                if "BUY" in output.upper(): decision = "BUY"
                elif "SELL" in output.upper(): decision = "SELL"
                
                # Extract numbers from confidence
                conf_match = re.search(r'CONFIDENCE:\s*(\d+)', output, re.IGNORECASE)
                if conf_match:
                    confidence = float(conf_match.group(1))
            except Exception:
                pass # Default to HOLD 0% if parsing fails
            
            # 3. Apply Risk Management (Position Sizing based on Confidence)
            # Only risk a maximum of 5% of capital per trade, scaled by confidence
            max_risk_amount = capital * 0.05
            position_size = max_risk_amount * (confidence / 100.0)
            
            price_change_pct = (actual_next_price - current_price) / current_price
            
            trade_pnl = 0.0
            if decision == "BUY" and confidence > 50: # Only trade if confident
                trade_pnl = position_size * price_change_pct
                if trade_pnl > 0: win_count += 1
                else: loss_count += 1
            elif decision == "SELL" and confidence > 50:
                trade_pnl = position_size * -price_change_pct # Short selling
                if trade_pnl > 0: win_count += 1
                else: loss_count += 1
                
            capital += trade_pnl
            
            print(f"Date: {current_date} | AI: {decision:<4} (Conf: {confidence:3.0f}%) | "
                  f"Pos Size: ${position_size:5.0f} | PnL: ${trade_pnl:6.2f} | Portfolio: ${capital:,.2f}")
                  
        print("\n========== BACKTEST RESULTS ==========")
        print(f"Starting Capital: ${initial_capital:,.2f}")
        print(f"Ending Capital:   ${capital:,.2f}")
        
        total_return = ((capital - initial_capital) / initial_capital) * 100
        print(f"Total Return:     {total_return:+.2f}%")
        
        total_trades = win_count + loss_count
        if total_trades > 0:
            win_rate = (win_count / total_trades) * 100
            print(f"Win Rate:         {win_rate:.1f}% ({win_count} Wins, {loss_count} Losses)")

if __name__ == "__main__":
    tester = AgentBacktester()
    tester.run_backtest("AAPL", days_to_test=10)