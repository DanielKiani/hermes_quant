import yfinance as yf
import pandas as pd
import os

def download_daily_data(ticker, period="2y"):
    """
    Downloads historical daily data for a given ticker and saves it to the data folder.
    
    Args:
        ticker (str): Stock ticker symbol (e.g., "AAPL").
        period (str): Lookback period (e.g., "1y", "2y", "max").
        
    Returns:
        pd.DataFrame: Cleaned historical data.
    """
    print(f"Downloading data for {ticker}...")
    stock = yf.Ticker(ticker)
    df = stock.history(period=period)
    
    if df.empty:
        raise ValueError(f"No data found for ticker {ticker}.")
    
    # Clean up the dataframe
    df = df.reset_index()
    # Handle timezone-aware datetimes
    df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None).dt.date
    
    # Ensure the data folder exists
    os.makedirs("data", exist_ok=True)
    
    # Save to CSV for local caching
    filepath = f"data/{ticker}_daily.csv"
    df.to_csv(filepath, index=False)
    print(f"Data saved to {filepath}")
    
    return df

def get_closing_prices(ticker):
    """
    Helper function to load cached data and return just the closing prices 
    as a numpy array for the TimesFM model.
    """
    filepath = f"data/{ticker}_daily.csv"
    if not os.path.exists(filepath):
        print(f"Cache miss. Downloading {ticker}...")
        df = download_daily_data(ticker)
    else:
        df = pd.read_csv(filepath)
        
    return df['Close'].values

def get_technical_indicators(ticker):
    """
    Calculates standard momentum and trend indicators.
    """
    filepath = f"data/{ticker}_daily.csv"
    df = pd.read_csv(filepath)
    
    if len(df) < 30:
        return "Not enough data for technicals."
        
    # Calculate 20-day Simple Moving Average (Trend)
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    
    # Calculate RSI (Momentum)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI_14'] = 100 - (100 / (1 + rs))
    
    # Calculate MACD (Trend Momentum)
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    
    # Get the latest day's data
    latest = df.iloc[-1]
    
    tech_text = f"20-Day SMA: ${latest['SMA_20']:.2f}\n"
    tech_text += f"14-Day RSI: {latest['RSI_14']:.2f} (Over 70 is overbought, under 30 is oversold)\n"
    tech_text += f"MACD: {latest['MACD']:.2f}\n"
    
    return tech_text

def get_macro_environment():
    """
    Fetches high-level macroeconomic indicators to provide market context.
    Uses the 10-Year Treasury Yield (proxy for interest rates) and S&P 500.
    """
    # ^TNX is the 10-Year Treasury Yield (Interest rates)
    # ^GSPC is the S&P 500 Index
    tnx = yf.Ticker("^TNX").history(period="5d")
    sp500 = yf.Ticker("^GSPC").history(period="5d")
    
    try:
        tnx_latest = tnx['Close'].iloc[-1]
        sp500_latest = sp500['Close'].iloc[-1]
        macro_text = f"10-Year Treasury Yield (Interest Rates): {tnx_latest:.2f}%\n"
        macro_text += f"S&P 500 Index Level: {sp500_latest:.2f}\n"
    except IndexError:
        macro_text = "Macro data currently unavailable.\n"
        
    return macro_text

if __name__ == "__main__":
    # Test the function with Apple
    df = download_daily_data("AAPL", period="2y")
    print("\nData Tail:")
    print(df.tail())