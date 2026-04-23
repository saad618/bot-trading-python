import pandas as pd
from strategies.base import TradingStrategy

class CandlestickPatternStrategy(TradingStrategy):
    def name(self) -> str:
        return "CDL"

    def score(self, df: pd.DataFrame) -> int:
        if len(df) < 2:
            return 0

        t, y = df.iloc[0], df.iloc[1]
        body = abs(t["close"] - t["open"])
        rng = t["high"] - t["low"]

        # Bullish engulfing
        if (t["close"] > t["open"] and y["close"] < y["open"]
                and t["open"] <= y["close"] and t["close"] >= y["open"]):
            return 1

        # Hammer
        if t["close"] > t["open"] and body > 0 and rng > 0:
            lower_shadow = min(t["open"], t["close"]) - t["low"]
            if lower_shadow >= 2 * body:
                return 1

        # Bearish engulfing
        if (t["close"] < t["open"] and y["close"] > y["open"]
                and t["open"] >= y["close"] and t["close"] <= y["open"]):
            return -1

        # Shooting star
        if t["close"] < t["open"] and body > 0 and rng > 0:
            upper_shadow = t["high"] - max(t["open"], t["close"])
            if upper_shadow >= 2 * body:
                return -1

        return 0
