from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


class BacktestRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=15)
    engine: str = Field(default="auto", pattern="^(auto|xgboost|logistic|sma)$")
    asset_class: str = Field(default="equity", pattern="^(equity|crypto)$")
    train_window: int = Field(default=750, ge=100, le=2_500)
    test_window: int = Field(default=63, ge=10, le=252)
    validation_fraction: float = Field(default=0.2, ge=0.1, le=0.4)
    transaction_cost_bps: float = Field(default=5.0, ge=0, le=100)
    slippage_bps: float = Field(default=2.0, ge=0, le=100)
    use_regime_filter: bool = False
    n_trials: int = Field(default=10, ge=1, le=30)
    target_horizon: int = Field(default=5, ge=1, le=20)
    long_threshold: float = Field(default=0.54, gt=0.5, lt=0.9)
    short_threshold: float = Field(default=0.46, gt=0.1, lt=0.5)
    position_mode: str = Field(default="long_cash", pattern="^(long_cash|long_short)$")
    risk_free_rate: float = Field(default=0.0, ge=0, le=25)
    lookback_years: int = Field(default=10, ge=3, le=15)
    short_window: int = Field(default=20, ge=2, le=200)
    long_window: int = Field(default=50, ge=5, le=400)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def validate_sma_windows(self):
        if self.engine == "sma" and self.short_window >= self.long_window:
            raise ValueError("short_window must be smaller than long_window.")
        if self.short_threshold >= self.long_threshold:
            raise ValueError("short_threshold must be smaller than long_threshold.")
        return self


class AnalysisRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=15)
    model: str = Field(default="XGBoost", pattern="^(XGBoost|TimesFM)$")

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()


class Position(BaseModel):
    ticker: str = Field(min_length=1, max_length=15)
    quantity: float = Field(gt=0, le=1_000_000_000)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()


class PortfolioRequest(BaseModel):
    positions: list[Position] = Field(min_length=1, max_length=25)
    confidence: float = Field(default=0.95, ge=0.9, le=0.99)

    @model_validator(mode="after")
    def require_unique_tickers(self):
        tickers = [position.ticker for position in self.positions]
        if len(tickers) != len(set(tickers)):
            raise ValueError("Portfolio tickers must be unique.")
        return self
