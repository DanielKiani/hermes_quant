"""Purged walk-forward research engines for daily market data.

The module treats XGBoost and logistic regression as candidates, not as proof
of alpha. Model selection is confined to a chronological validation slice and
an embargo separates every training window from the following evaluation data.
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np
import optuna
import pandas as pd
import xgboost as xgb
import yfinance as yf
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, brier_score_loss, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


FEATURES = [
    "Return_1",
    "Return_5",
    "Return_20",
    "SMA_Ratio_20",
    "SMA_Ratio_50",
    "Volatility_20",
    "RSI_14",
    "Range_Pct",
    "Volume_Z20",
    "Drawdown_63",
    "Reference_Return_5",
    "Reference_Trend_200",
]


class MLQuantBacktester:
    def __init__(
        self,
        ticker: str,
        start_date: str = "2016-01-01",
        market_data: pd.DataFrame | None = None,
        spy_data: pd.DataFrame | None = None,
        asset_class: str | None = None,
    ):
        self.ticker = ticker.upper().strip()
        self.start_date = start_date
        self.asset_class = asset_class or ("crypto" if self.ticker.endswith("-USD") else "equity")
        self.reference_symbol = "BTC-USD" if self.asset_class == "crypto" else "SPY"
        self.annualization_factor = 365 if self.asset_class == "crypto" else 252
        self.df = self._load_and_prep_data(market_data, spy_data)

    @staticmethod
    def _normalize_download(frame: pd.DataFrame) -> pd.DataFrame:
        frame = frame.copy()
        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = frame.columns.droplevel(1)
        if "Date" not in frame.columns:
            frame = frame.reset_index()
        frame["Date"] = pd.to_datetime(frame["Date"]).dt.tz_localize(None)
        return frame

    def _download_with_retry(self, ticker: str) -> pd.DataFrame:
        frame = pd.DataFrame()
        for attempt in range(3):
            frame = yf.download(
                ticker,
                start=self.start_date,
                auto_adjust=True,
                progress=False,
            )
            if not frame.empty:
                return frame
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
        return frame

    def _load_and_prep_data(
        self,
        market_data: pd.DataFrame | None,
        reference_data: pd.DataFrame | None,
    ) -> pd.DataFrame:
        raw_market = market_data if market_data is not None else self._download_with_retry(self.ticker)
        if raw_market.empty:
            raise ValueError(f"No market data returned for {self.ticker}.")
        df = self._normalize_download(raw_market)

        raw_reference = reference_data
        if raw_reference is None:
            raw_reference = self._download_with_retry(self.reference_symbol)
        if raw_reference.empty:
            raise ValueError(f"No reference data returned for {self.reference_symbol}.")
        reference = self._normalize_download(raw_reference)
        reference = reference[["Date", "Close"]].rename(columns={"Close": "Reference_Close"})
        reference["Reference_SMA_200"] = reference["Reference_Close"].rolling(200).mean()
        reference["Reference_Return_5"] = reference["Reference_Close"].pct_change(5)

        df = pd.merge(df, reference, on="Date", how="left")
        df[["Reference_Close", "Reference_SMA_200", "Reference_Return_5"]] = df[
            ["Reference_Close", "Reference_SMA_200", "Reference_Return_5"]
        ].ffill()

        close = df["Close"].astype(float)
        returns = close.pct_change()
        sma20 = close.rolling(20).mean()
        sma50 = close.rolling(50).mean()
        df["Return_1"] = returns
        df["Return_5"] = close.pct_change(5)
        df["Return_20"] = close.pct_change(20)
        df["SMA_Ratio_20"] = close / sma20 - 1
        df["SMA_Ratio_50"] = close / sma50 - 1
        df["Volatility_20"] = returns.rolling(20).std()

        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = -delta.clip(upper=0).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        df["RSI_14"] = (100 - (100 / (1 + rs))) / 100
        df["Range_Pct"] = (df["High"].astype(float) - df["Low"].astype(float)) / close
        log_volume = np.log1p(df.get("Volume", pd.Series(0, index=df.index)).fillna(0).astype(float))
        volume_std = log_volume.rolling(20).std().replace(0, np.nan)
        df["Volume_Z20"] = ((log_volume - log_volume.rolling(20).mean()) / volume_std).fillna(0)
        df["Drawdown_63"] = close / close.rolling(63).max() - 1
        df["Reference_Trend_200"] = df["Reference_Close"] / df["Reference_SMA_200"] - 1
        df["Returns"] = returns
        df["SPY_Close"] = df["Reference_Close"]
        df["SPY_SMA_200"] = df["Reference_SMA_200"]
        df = df.dropna(subset=FEATURES).reset_index(drop=True)
        return self._with_target(df, 5)

    @staticmethod
    def _with_target(frame: pd.DataFrame, horizon: int) -> pd.DataFrame:
        output = frame.copy()
        future_close = output["Close"].shift(-horizon)
        output["Target"] = np.where(
            future_close.notna(),
            (future_close > output["Close"]).astype(float),
            np.nan,
        )
        return output

    @staticmethod
    def _split_training_window(
        train_df: pd.DataFrame,
        validation_fraction: float,
        gap: int = 0,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        if not 0.1 <= validation_fraction <= 0.4:
            raise ValueError("validation_fraction must be between 0.1 and 0.4.")
        if gap < 0:
            raise ValueError("gap cannot be negative.")
        validation_size = max(10, int(len(train_df) * validation_fraction))
        inner_end = len(train_df) - validation_size - gap
        if inner_end < 30:
            raise ValueError("Training window is too small for a purged validation split.")
        return train_df.iloc[:inner_end], train_df.iloc[-validation_size:]

    @staticmethod
    def _trial_params(trial: optuna.Trial) -> dict[str, Any]:
        return {
            "max_depth": trial.suggest_int("max_depth", 2, 5),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.15, log=True),
            "n_estimators": trial.suggest_int("n_estimators", 60, 240),
            "subsample": trial.suggest_float("subsample", 0.65, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "min_child_weight": trial.suggest_int("min_child_weight", 2, 12),
            "reg_lambda": trial.suggest_float("reg_lambda", 0.5, 8.0, log=True),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-4, 1.0, log=True),
        }

    @staticmethod
    def _new_xgboost(params: dict[str, Any]) -> xgb.XGBClassifier:
        return xgb.XGBClassifier(
            **params,
            objective="binary:logistic",
            random_state=42,
            eval_metric="logloss",
            tree_method="hist",
            n_jobs=1,
        )

    @staticmethod
    def _new_logistic() -> Pipeline:
        return Pipeline(
            [
                ("scale", StandardScaler()),
                ("model", LogisticRegression(C=0.3, max_iter=2_000, random_state=42)),
            ]
        )

    @staticmethod
    def _quality(y_true: pd.Series, probability: np.ndarray) -> dict[str, float]:
        predicted = (probability >= 0.5).astype(int)
        return {
            "accuracy": float(accuracy_score(y_true, predicted)),
            "balanced_accuracy": float(balanced_accuracy_score(y_true, predicted)),
            "log_loss": float(log_loss(y_true, probability, labels=[0, 1])),
            "brier_score": float(brier_score_loss(y_true, probability)),
            "positive_rate": float(np.mean(predicted)),
        }

    def _tune_on_inner_validation(
        self,
        train_df: pd.DataFrame,
        feature_cols: list[str],
        validation_fraction: float,
        n_trials: int,
        gap: int = 5,
    ) -> tuple[dict[str, Any], float, pd.DataFrame, pd.DataFrame]:
        inner_train, validation = self._split_training_window(
            train_df, validation_fraction, gap
        )
        if inner_train["Target"].nunique() < 2:
            raise ValueError("The inner training window contains only one target class.")

        def objective(trial: optuna.Trial) -> float:
            model = self._new_xgboost(self._trial_params(trial))
            model.fit(inner_train[feature_cols], inner_train["Target"])
            probability = model.predict_proba(validation[feature_cols])[:, 1]
            return float(log_loss(validation["Target"], probability, labels=[0, 1]))

        optuna.logging.set_verbosity(optuna.logging.WARNING)
        study = optuna.create_study(
            direction="minimize",
            sampler=optuna.samplers.TPESampler(seed=42),
        )
        study.optimize(objective, n_trials=n_trials)
        return study.best_params, float(study.best_value), inner_train, validation

    def _candidate_for_fold(
        self,
        engine: str,
        train_data: pd.DataFrame,
        validation_fraction: float,
        n_trials: int,
        gap: int,
    ) -> tuple[str, Any, dict[str, float], dict[str, Any]]:
        if engine == "logistic":
            inner_train, validation = self._split_training_window(
                train_data, validation_fraction, gap
            )
            logistic_model = self._new_logistic()
            logistic_model.fit(inner_train[FEATURES], inner_train["Target"])
            logistic_quality = self._quality(
                validation["Target"],
                logistic_model.predict_proba(validation[FEATURES])[:, 1],
            )
            return "Logistic regression", self._new_logistic(), logistic_quality, {"C": 0.3}

        best_params, _, inner_train, validation = self._tune_on_inner_validation(
            train_data,
            FEATURES,
            validation_fraction,
            n_trials,
            gap,
        )
        xgb_model = self._new_xgboost(best_params)
        xgb_model.fit(inner_train[FEATURES], inner_train["Target"])
        xgb_quality = self._quality(
            validation["Target"], xgb_model.predict_proba(validation[FEATURES])[:, 1]
        )

        if engine == "xgboost":
            return "XGBoost", self._new_xgboost(best_params), xgb_quality, best_params

        logistic_model = self._new_logistic()
        logistic_model.fit(inner_train[FEATURES], inner_train["Target"])
        logistic_quality = self._quality(
            validation["Target"], logistic_model.predict_proba(validation[FEATURES])[:, 1]
        )
        if logistic_quality["log_loss"] <= xgb_quality["log_loss"]:
            return "Logistic regression", self._new_logistic(), logistic_quality, {"C": 0.3}
        return "XGBoost", self._new_xgboost(best_params), xgb_quality, best_params

    @staticmethod
    def _signals(
        probability: np.ndarray,
        long_threshold: float,
        short_threshold: float,
        position_mode: str,
    ) -> np.ndarray:
        signal = np.zeros(len(probability), dtype=int)
        signal[probability >= long_threshold] = 1
        if position_mode == "long_short":
            signal[probability <= short_threshold] = -1
        return signal

    def run_walk_forward_xgboost(
        self,
        train_window: int = 750,
        test_window: int = 63,
        use_regime_filter: bool = False,
        validation_fraction: float = 0.2,
        transaction_cost_bps: float = 5.0,
        n_trials: int = 10,
        engine: str = "xgboost",
        target_horizon: int = 5,
        long_threshold: float = 0.54,
        short_threshold: float = 0.46,
        position_mode: str = "long_cash",
        slippage_bps: float = 2.0,
        risk_free_rate: float = 0.0,
    ) -> dict:
        if engine not in {"xgboost", "logistic", "auto"}:
            raise ValueError(f"Unsupported model engine: {engine}.")
        if transaction_cost_bps < 0 or slippage_bps < 0:
            raise ValueError("Costs and slippage cannot be negative.")
        if n_trials < 1:
            raise ValueError("n_trials must be at least 1.")
        if not 1 <= target_horizon <= 20:
            raise ValueError("target_horizon must be between 1 and 20 observations.")
        if not 0 < short_threshold < long_threshold < 1:
            raise ValueError("Probability thresholds must satisfy 0 < short < long < 1.")

        bt_df = self._with_target(self.df.drop(columns=["Target"]), target_horizon)
        bt_df = bt_df.dropna(subset=["Target"]).reset_index(drop=True)
        embargo = target_horizon
        if len(bt_df) < train_window + embargo + test_window:
            raise ValueError("Not enough historical data for the requested windows and embargo.")

        results: list[pd.DataFrame] = []
        folds: list[dict[str, Any]] = []
        selections: dict[str, int] = {"XGBoost": 0, "Logistic regression": 0}
        last_start = len(bt_df) - train_window - embargo - test_window

        for start_idx in range(0, last_start + 1, test_window):
            train_end = start_idx + train_window
            test_start = train_end + embargo
            train_data = bt_df.iloc[start_idx:train_end].copy()
            test_data = bt_df.iloc[test_start : test_start + test_window].copy()

            selected, model, validation_quality, params = self._candidate_for_fold(
                engine,
                train_data,
                validation_fraction,
                n_trials,
                embargo,
            )
            model.fit(train_data[FEATURES], train_data["Target"])
            probability = model.predict_proba(test_data[FEATURES])[:, 1]
            test_quality = self._quality(test_data["Target"], probability)
            test_data["Model_Probability"] = probability
            test_data["ML_Signal"] = self._signals(
                probability,
                long_threshold,
                short_threshold,
                position_mode,
            )
            if use_regime_filter:
                risk_off = test_data["Reference_Close"] < test_data["Reference_SMA_200"]
                test_data.loc[risk_off.fillna(False) & (test_data["ML_Signal"] > 0), "ML_Signal"] = 0

            day = lambda value: pd.Timestamp(value).date().isoformat()
            inner_train, validation = self._split_training_window(
                train_data, validation_fraction, embargo
            )
            folds.append(
                {
                    "train_start": day(train_data["Date"].iloc[0]),
                    "train_end": day(train_data["Date"].iloc[-1]),
                    "validation_start": day(validation["Date"].iloc[0]),
                    "validation_end": day(validation["Date"].iloc[-1]),
                    "test_start": day(test_data["Date"].iloc[0]),
                    "test_end": day(test_data["Date"].iloc[-1]),
                    "embargo_observations": embargo,
                    "selected_model": selected,
                    "validation_accuracy": validation_quality["accuracy"],
                    "validation_balanced_accuracy": validation_quality["balanced_accuracy"],
                    "validation_log_loss": validation_quality["log_loss"],
                    "test_accuracy": test_quality["accuracy"],
                    "test_balanced_accuracy": test_quality["balanced_accuracy"],
                    "test_log_loss": test_quality["log_loss"],
                    "test_brier_score": test_quality["brier_score"],
                    "parameters": params,
                }
            )
            selections[selected] += 1
            results.append(test_data)

        if not results:
            raise ValueError("No complete walk-forward fold could be constructed.")

        result = pd.concat(results, ignore_index=True)
        position = result["ML_Signal"].shift(1).fillna(0)
        turnover = position.diff().abs().fillna(position.abs())
        costs = turnover * ((transaction_cost_bps + slippage_bps) / 10_000)
        result["Strategy_Return"] = position * result["Returns"] - costs
        result["Cumulative_Market"] = (1 + result["Returns"]).cumprod()
        result["Cumulative_Strategy"] = (1 + result["Strategy_Return"]).cumprod()
        result["Position"] = position
        result["Turnover"] = turnover
        result["Drawdown"] = result["Cumulative_Strategy"] / result["Cumulative_Strategy"].cummax() - 1

        metrics = self._performance_metrics(result, costs, risk_free_rate)
        selection_rule = {
            "xgboost": "XGBoost parameters minimize validation log loss inside each purged training window",
            "logistic": "Fixed regularized logistic baseline evaluated on each purged validation window",
            "auto": "Lowest validation log loss selects XGBoost or logistic regression independently per fold",
        }[engine]
        return {
            "data": result[
                [
                    "Date",
                    "Close",
                    "Cumulative_Market",
                    "Cumulative_Strategy",
                    "ML_Signal",
                    "Model_Probability",
                    "Position",
                    "Turnover",
                    "Drawdown",
                    "Strategy_Return",
                ]
            ],
            **metrics,
            "evidence": {
                "ticker": self.ticker,
                "engine": engine,
                "asset_class": self.asset_class,
                "target": f"positive close-to-close return {target_horizon} observations ahead",
                "target_horizon": target_horizon,
                "selection_rule": selection_rule,
                "outer_test_policy": "never used for hyperparameter or model selection",
                "embargo_observations": embargo,
                "train_window": train_window,
                "test_window": test_window,
                "validation_fraction": validation_fraction,
                "transaction_cost_bps": transaction_cost_bps,
                "slippage_bps": slippage_bps,
                "long_threshold": long_threshold,
                "short_threshold": short_threshold,
                "position_mode": position_mode,
                "risk_free_rate_percent": risk_free_rate,
                "regime_filter": use_regime_filter,
                "regime_reference": f"{self.reference_symbol} 200-day trend",
                "annualization_factor": self.annualization_factor,
                "features": FEATURES,
                "model_selections": selections,
                "folds": folds,
                "limitations": [
                    "Historical daily-close research; not live or broker-executed performance.",
                    "Signals are executed with a one-observation lag; overlapping horizon labels remain a diagnostic limitation.",
                    "Configured costs and slippage are deterministic; spread variation and market impact are excluded.",
                    "Short borrow, funding, taxes, and survivorship effects are not modeled.",
                ],
            },
        }

    def _performance_metrics(
        self,
        frame: pd.DataFrame,
        costs: pd.Series,
        risk_free_rate: float,
    ) -> dict[str, float | int]:
        strategy_return = (frame["Cumulative_Strategy"].iloc[-1] - 1) * 100
        market_return = (frame["Cumulative_Market"].iloc[-1] - 1) * 100
        years = len(frame) / self.annualization_factor
        terminal = frame["Cumulative_Strategy"].iloc[-1]
        cagr = terminal ** (1 / years) - 1 if years > 0 and terminal > 0 else -1.0
        volatility = frame["Strategy_Return"].std() * np.sqrt(self.annualization_factor)
        daily_risk_free = (1 + risk_free_rate / 100) ** (1 / self.annualization_factor) - 1
        excess = frame["Strategy_Return"] - daily_risk_free
        sharpe = excess.mean() * self.annualization_factor / volatility if volatility > 0 else 0.0
        downside = frame.loc[frame["Strategy_Return"] < 0, "Strategy_Return"].std()
        sortino = excess.mean() * self.annualization_factor / (downside * np.sqrt(self.annualization_factor)) if downside > 0 else 0.0
        max_drawdown = frame["Drawdown"].min() * 100
        calmar = cagr / abs(max_drawdown / 100) if max_drawdown < 0 else 0.0
        active = frame["Position"] != 0
        hit_rate = (frame.loc[active, "Strategy_Return"] > 0).mean() * 100 if active.any() else 0.0
        return {
            "Return_Pct": float(strategy_return),
            "Market_Return_Pct": float(market_return),
            "Annualized_Return_Pct": float(cagr * 100),
            "Annualized_Volatility_Pct": float(volatility * 100),
            "Sharpe_Ratio": float(sharpe),
            "Sortino_Ratio": float(sortino),
            "Calmar_Ratio": float(calmar),
            "Max_Drawdown_Pct": float(max_drawdown),
            "Total_Trades": int((frame["Turnover"] > 0).sum()),
            "Turnover": float(frame["Turnover"].sum()),
            "Exposure_Pct": float(frame["Position"].abs().mean() * 100),
            "Hit_Rate_Pct": float(hit_rate),
            "Total_Cost_Pct": float(costs.sum() * 100),
        }

    def _engineer_features(self) -> tuple[pd.DataFrame, list[str]]:
        return self.df, FEATURES

    def _optimize_hyperparameters(
        self,
        train_df: pd.DataFrame,
        feature_cols: list[str],
        n_trials: int = 10,
        validation_fraction: float = 0.2,
    ) -> dict[str, Any]:
        best_params, _, _, _ = self._tune_on_inner_validation(
            train_df,
            feature_cols,
            validation_fraction,
            n_trials,
            gap=5,
        )
        return best_params

    def predict_today(self) -> dict[str, float | str]:
        """Select a candidate on purged validation, then estimate the latest horizon."""
        train_df = self.df.dropna(subset=["Target"]).copy()
        selected, model, quality, _ = self._candidate_for_fold(
            "auto",
            train_df,
            validation_fraction=0.2,
            n_trials=10,
            gap=5,
        )
        model.fit(train_df[FEATURES], train_df["Target"])
        latest = self.df.iloc[-1:]
        probability_up = float(model.predict_proba(latest[FEATURES])[0][1])
        return {
            "probability_up": probability_up,
            "rsi": float(latest["RSI_14"].iloc[0] * 100),
            "volatility": float(latest["Volatility_20"].iloc[0]),
            "classification": "predicted",
            "method": f"purged-validation-selected {selected}",
            "validation_log_loss": quality["log_loss"],
        }
