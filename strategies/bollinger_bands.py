import pandas as pd
from strategies.base import TradingStrategy

class BollingerBandsStrategy(TradingStrategy):
    def __init__(self, period=20, std_dev=2.0):
        self.period = period
        self.std_dev = std_dev

    def name(self) -> str:
        return "BB"

    def score(self, df: pd.DataFrame) -> int:
        if len(df) < self.period:
            return 0

        closes = df["close"].values[:self.period]
        middle = closes.mean()
        std    = closes.std()
        upper  = middle + self.std_dev * std
        lower  = middle - self.std_dev * std

        price = df.iloc[0]["close"]

        if price <= lower:
            return 1   # oversold — potential bounce up
        if price >= upper:
            return -1  # overbought — potential drop
        # Price in lower half of band (mild bullish)
        if price < middle:
            return 0
        return 0
