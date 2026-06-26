import lightning as L
import torch
import numpy as np
import timesfm

class TimesFMPredictor(L.LightningModule):
    def __init__(self, context_len=1024, horizon_len=10):
        """
        Initializes the TimesFM foundation model.
        
        Args:
            context_len (int): How many past days to look at (max 16384 for v2.5).
            horizon_len (int): How many future days to predict.
        """
        super().__init__()
        self.context_len = context_len
        self.horizon_len = horizon_len
        
        # Optimize PyTorch matrix math for your CPU architecture
        torch.set_float32_matmul_precision("high")
        
        print("Loading TimesFM 2.5 200M Foundation Model...")
        # Load the PyTorch version of TimesFM directly from HuggingFace
        self.model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(
            "google/timesfm-2.5-200m-pytorch"
        )
        
        # Compile the model with specific configurations for financial data
        self.model.compile(timesfm.ForecastConfig(
            max_context=self.context_len,
            max_horizon=self.horizon_len,
            normalize_inputs=True,           # Crucial for financial data
            use_continuous_quantile_head=True, # Gives us probability bands (P10 to P90)
            infer_is_positive=False          # Set False because returns/changes can be negative
        ))
        print("Model loaded and compiled successfully.")

    def forward(self, historical_prices):
        """
        Runs the zero-shot prediction.
        
        Args:
            historical_prices (np.ndarray): 1D array of recent closing prices.
            
        Returns:
            dict: Contains the median prediction and the confidence intervals.
        """
        # TimesFM expects a list of arrays (batching support)
        inputs = [historical_prices.astype(np.float32)]
        
        # Run inference
        point_forecast, quantile_forecast = self.model.forecast(
            horizon=self.horizon_len, 
            inputs=inputs
        )
        
        # point_forecast shape: (1, horizon_len) -> median prediction
        # quantile_forecast shape: (1, horizon_len, 10) -> P10 through P90 percentiles
        
        return {
            "median": point_forecast[0],
            "p10": quantile_forecast[0, :, 1], # 10th percentile (bearish bound)
            "p90": quantile_forecast[0, :, 9]  # 90th percentile (bullish bound)
        }

    def predict_step(self, batch, batch_idx):
        """
        PyTorch Lightning standard prediction hook.
        Used if you want to run massive multi-stock backtests via a DataLoader.
        """
        x = batch
        return self.forward(x)

# Quick local test if you run this script directly
if __name__ == "__main__":
    # Simulate 100 days of random walk stock data
    dummy_data = np.cumsum(np.random.randn(100)) + 150 
    
    predictor = TimesFMPredictor(context_len=1024, horizon_len=5)
    forecast = predictor(dummy_data)
    
    print(f"\nNext 5 days point forecast:\n{forecast['median']}")
    print(f"90th Percentile (Upper Bound):\n{forecast['p90']}")
    print(f"10th Percentile (Lower Bound):\n{forecast['p10']}")