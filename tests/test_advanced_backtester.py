from __future__ import annotations

import numpy as np
import pandas as pd

from src.advanced_backtester import FEATURES, MLQuantBacktester


def price_frame(days: int = 320, start: str = "2020-01-01") -> pd.DataFrame:
    dates = pd.date_range(start, periods=days, freq="B")
    trend = np.linspace(100, 180, days)
    cycle = np.sin(np.arange(days) / 4) * 3
    close = trend + cycle
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": close - 0.4,
            "High": close + 1,
            "Low": close - 1,
            "Close": close,
            "Volume": np.linspace(1_000_000, 1_300_000, days),
        }
    )


def make_engine(days: int = 320) -> MLQuantBacktester:
    market = price_frame(days)
    spy = price_frame(days)
    return MLQuantBacktester("TEST", market_data=market, spy_data=spy)


def test_future_target_is_unknown_for_final_five_rows() -> None:
    engine = make_engine()
    assert engine.df["Target"].tail(5).isna().all()
    assert engine.df["Target"].iloc[:-5].notna().all()


def test_inner_validation_is_chronological_and_disjoint() -> None:
    engine = make_engine(500)
    known = engine.df.dropna(subset=["Target"]).iloc[:120]
    inner_train, validation = engine._split_training_window(known, 0.2)
    assert len(inner_train) == 96
    assert len(validation) == 24
    assert inner_train["Date"].max() < validation["Date"].min()
    assert set(inner_train.index).isdisjoint(validation.index)


def test_outer_test_is_not_passed_to_tuning(monkeypatch) -> None:
    engine = make_engine(520)
    tuned_windows: list[tuple[pd.Timestamp, pd.Timestamp]] = []

    def fake_tune(train_df, feature_cols, validation_fraction, n_trials, gap=5):
        assert feature_cols == FEATURES
        inner, validation = engine._split_training_window(train_df, validation_fraction, gap)
        tuned_windows.append((train_df["Date"].min(), train_df["Date"].max()))
        params = {"max_depth": 2, "learning_rate": 0.1, "n_estimators": 2, "subsample": 1.0}
        return params, 0.5, inner, validation

    monkeypatch.setattr(engine, "_tune_on_inner_validation", fake_tune)
    result = engine.run_walk_forward_xgboost(
        train_window=100,
        test_window=20,
        validation_fraction=0.2,
        transaction_cost_bps=5,
        n_trials=1,
    )

    folds = result["evidence"]["folds"]
    assert folds
    assert len(folds) == len(tuned_windows)
    for tuned, fold in zip(tuned_windows, folds, strict=True):
        assert tuned[1].date().isoformat() == fold["train_end"]
        assert fold["train_end"] < fold["test_start"]
        assert fold["validation_end"] < fold["test_start"]
    assert result["evidence"]["outer_test_policy"] == "never used for hyperparameter or model selection"
    assert result["evidence"]["transaction_cost_bps"] == 5
    assert result["evidence"]["embargo_observations"] == 5


def test_purged_validation_gap_separates_label_horizon() -> None:
    engine = make_engine(500)
    known = engine.df.dropna(subset=["Target"]).iloc[:180]
    inner_train, validation = engine._split_training_window(known, 0.2, gap=5)
    assert len(known) - len(inner_train) - len(validation) == 5
    assert inner_train["Date"].max() < validation["Date"].min()
