import pandas as pd
import numpy as np
import yfinance as yf
import xgboost as xgb
import optuna
import warnings

# Suppress warnings for clean output
warnings.filterwarnings('ignore')

class MLQuantBacktester:
    def __init__(self, ticker, start_date="2016-01-01"):
        self.ticker = ticker
        self.start_date = start_date
        self.df = self._load_and_prep_data()

    def _load_and_prep_data(self):
        """Downloads data, engineers features, and merges SPY data for regime filtering."""
        df = yf.download(self.ticker, start=self.start_date, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
        
        df.reset_index(inplace=True)
        df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)
        
        # Download SPY for the Regime Filter
        spy = yf.download("SPY", start=self.start_date, progress=False)
        if isinstance(spy.columns, pd.MultiIndex):
            spy.columns = spy.columns.droplevel(1)
        spy.reset_index(inplace=True)
        spy['Date'] = pd.to_datetime(spy['Date']).dt.tz_localize(None)
        
        spy = spy[['Date', 'Close']].rename(columns={'Close': 'SPY_Close'})
        spy['SPY_SMA_200'] = spy['SPY_Close'].rolling(window=200).mean()
        
        # Merge SPY data onto the main dataframe
        df = pd.merge(df, spy, on='Date', how='left')
        df['SPY_Close'] = df['SPY_Close'].ffill()
        df['SPY_SMA_200'] = df['SPY_SMA_200'].ffill()
        
        # Core Technical Features
        df['Returns'] = df['Close'].pct_change()
        df['SMA_20'] = df['Close'].rolling(window=20).mean()
        df['SMA_50'] = df['Close'].rolling(window=50).mean()
        df['Volatility_20'] = df['Returns'].rolling(window=20).std()
        
        # Momentum (RSI proxy)
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI_14'] = 100 - (100 / (1 + rs))

        # Target: Predict if the price will be higher 5 days from now (Swing Trading)
        df['Target'] = (df['Close'].shift(-5) > df['Close']).astype(int)
        
        # Drop initial NaNs from rolling windows, but keep the trailing NaNs for live prediction
        df = df.dropna(subset=['Returns', 'SMA_50', 'Volatility_20', 'RSI_14'])
        return df

    def run_walk_forward_xgboost(self, train_window=750, test_window=63, use_regime_filter=False):
        """Executes the institutional walk-forward backtest."""
        features = ['Returns', 'SMA_20', 'SMA_50', 'Volatility_20', 'RSI_14']
        
        # Drop the last 5 days where the target is inherently NaN
        bt_df = self.df.dropna(subset=['Target'])
        
        if len(bt_df) < train_window + test_window:
            raise ValueError("Not enough historical data for the specified walk-forward windows.")

        results = []
        
        # Walk-forward loop
        for start_idx in range(0, len(bt_df) - train_window - test_window, test_window):
            train_data = bt_df.iloc[start_idx : start_idx + train_window]
            test_data = bt_df.iloc[start_idx + train_window : start_idx + train_window + test_window]
            
            X_train, y_train = train_data[features], train_data['Target']
            X_test, y_test = test_data[features], test_data['Target']

            # Extremely fast, lightweight Bayesian Optimization
            def objective(trial):
                param = {
                    'max_depth': trial.suggest_int('max_depth', 3, 7),
                    'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.2),
                    'n_estimators': trial.suggest_int('n_estimators', 50, 200),
                    'subsample': trial.suggest_float('subsample', 0.6, 1.0),
                    'random_state': 42
                }
                model = xgb.XGBClassifier(**param, eval_metric='logloss')
                model.fit(X_train, y_train)
                preds = model.predict(X_test)
                return np.mean(preds == y_test)

            optuna.logging.set_verbosity(optuna.logging.WARNING)
            study = optuna.create_study(direction='maximize')
            study.optimize(objective, n_trials=10) 
            
            best_model = xgb.XGBClassifier(**study.best_params, random_state=42, eval_metric='logloss')
            best_model.fit(X_train, y_train)
            
            test_data = test_data.copy()
            test_data['ML_Signal'] = best_model.predict(X_test)
            
            # --- APPLY MACRO REGIME FILTER ---
            if use_regime_filter:
                # If SPY is below its 200 SMA, force the algorithm to hold cash (Signal = 0)
                bear_market_mask = test_data['SPY_Close'] < test_data['SPY_SMA_200']
                test_data.loc[bear_market_mask, 'ML_Signal'] = 0

            results.append(test_data)

        res_df = pd.concat(results)
        
        res_df['Strategy_Return'] = res_df['ML_Signal'].shift(1) * res_df['Returns']
        res_df['Cumulative_Market'] = (1 + res_df['Returns']).cumprod()
        res_df['Cumulative_Strategy'] = (1 + res_df['Strategy_Return'].fillna(0)).cumprod()

        strat_ret_pct = (res_df['Cumulative_Strategy'].iloc[-1] - 1) * 100
        mark_ret_pct = (res_df['Cumulative_Market'].iloc[-1] - 1) * 100
        
        annual_factor = 365 if self.ticker.endswith("-USD") else 252
        volatility = res_df['Strategy_Return'].std() * np.sqrt(annual_factor)
        sharpe = (res_df['Strategy_Return'].mean() * annual_factor) / volatility if volatility > 0 else 0
        
        rolling_max = res_df['Cumulative_Strategy'].cummax()
        drawdown = (res_df['Cumulative_Strategy'] / rolling_max) - 1
        max_dd_pct = drawdown.min() * 100
        
        total_trades = (res_df['ML_Signal'].diff().abs() > 0).sum()

        return {
            'data': res_df[['Date', 'Close', 'Cumulative_Market', 'Cumulative_Strategy', 'ML_Signal']],
            'Return_Pct': strat_ret_pct,
            'Market_Return_Pct': mark_ret_pct,
            'Sharpe_Ratio': sharpe,
            'Max_Drawdown_Pct': max_dd_pct,
            'Total_Trades': total_trades
        }

    def _engineer_features(self):
        """Helper to expose features for live predictions."""
        features = ['Returns', 'SMA_20', 'SMA_50', 'Volatility_20', 'RSI_14']
        return self.df, features

    def _optimize_hyperparameters(self, train_df, feature_cols, n_trials=10):
        """Runs optimization on the fly for predict_today."""
        def objective(trial):
            param = {
                'max_depth': trial.suggest_int('max_depth', 3, 7),
                'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.2),
                'n_estimators': trial.suggest_int('n_estimators', 50, 200),
                'subsample': trial.suggest_float('subsample', 0.6, 1.0),
                'random_state': 42
            }
            model = xgb.XGBClassifier(**param, eval_metric='logloss')
            model.fit(train_df[feature_cols], train_df['Target'])
            preds = model.predict(train_df[feature_cols])
            return np.mean(preds == train_df['Target'])
            
        optuna.logging.set_verbosity(optuna.logging.WARNING)
        study = optuna.create_study(direction='maximize')
        study.optimize(objective, n_trials=n_trials)
        return study.best_params

    def predict_today(self):
        """Generates a lightning-fast, real-time prediction for the LLM context."""
        features = ['Returns', 'SMA_20', 'SMA_50', 'Volatility_20', 'RSI_14']
        
        train_df = self.df.dropna(subset=['Target'])
        latest_features = self.df.iloc[-1:][features]
        
        best_params = self._optimize_hyperparameters(train_df, features, n_trials=10)
        
        model = xgb.XGBClassifier(**best_params, random_state=42, eval_metric='logloss')
        model.fit(train_df[features], train_df['Target'])
        
        prob_up = model.predict_proba(latest_features)[0][1]
        
        return {
            'probability_up': prob_up,
            'rsi': latest_features['RSI_14'].values[0],
            'volatility': latest_features['Volatility_20'].values[0]
        }