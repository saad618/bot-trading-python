import pandas as pd
from strategies.base import TradingStrategy

class RsiStrategy(TradingStrategy):
    def __init__(self, period: int = 14):
        self.period = period

    def name(self) -> str:
        return "RSI"

    def score(self, df: pd.DataFrame) -> int:
        if len(df) < self.period + 2:
            return 0

        closes = df["close"].values[::-1]  # oldest first
        changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]

        avg_gain = sum(max(0, c) for c in changes[:self.period]) / self.period
        avg_loss = sum(abs(min(0, c)) for c in changes[:self.period]) / self.period

        for c in changes[self.period:]:
            avg_gain = (avg_gain * (self.period - 1) + max(0, c)) / self.period
            avg_loss = (avg_loss * (self.period - 1) + abs(min(0, c))) / self.period

        rsi = 100.0 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))

        if rsi < 30:
            return 2    # extreme oversold
        if rsi < 45:
            return 1    # recovering from oversold
        if rsi > 70:
            return -2   # extreme overbought
        if rsi > 55:
            return -1   # approaching overbought
        return 0
