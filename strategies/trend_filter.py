import pandas as pd
from strategies.base import TradingStrategy

class TrendFilterStrategy(TradingStrategy):
    def name(self) -> str:
        return "TRD"

    def score(self, df: pd.DataFrame) -> int:
        if len(df) < 21:
            return 0

        prices = df["close"].values[::-1]  # oldest first

        def _ema(data, period):
            k = 2.0 / (period + 1)
            e = float(data[0])
            for p in data[1:period]:
                e = float(p) * k + e * (1 - k)
            return e

        current = float(df.iloc[0]["close"])

        ema5  = _ema(prices, 5)
        ema10 = _ema(prices, 10)
        ema20 = _ema(prices, 20)

        # Full bullish alignment: price > EMA5 > EMA10 > EMA20
        if current > ema5 > ema10 > ema20:
            return 1

        # Full bearish alignment: price < EMA5 < EMA10 < EMA20
        if current < ema5 < ema10 < ema20:
            return -1

        # Partial bullish: at least price above EMA20 and EMAs in order
        if current > ema20 and ema5 > ema10:
            return 1

        # Partial bearish: price below EMA20 and EMAs inverted
        if current < ema20 and ema5 < ema10:
            return -1

        return 0
