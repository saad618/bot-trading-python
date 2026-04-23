import pandas as pd
from strategies.base import TradingStrategy

class TrendFilterStrategy(TradingStrategy):
    def __init__(self, period: int = 50):
        self.period = period

    def name(self) -> str:
        return "TRD"

    def score(self, df: pd.DataFrame) -> int:
        if len(df) < self.period:
            return 0

        prices = df["close"].values[::-1][:self.period]  # oldest first
        k = 2.0 / (self.period + 1)
        ema = prices[0]
        for p in prices[1:]:
            ema = p * k + ema * (1 - k)

        current = df.iloc[0]["close"]
        if current > ema:
            return 1
        if current < ema:
            return -1
        return 0
