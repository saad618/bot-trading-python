import pandas as pd
from strategies.base import TradingStrategy

class RsiStrategy(TradingStrategy):
    def __init__(self, period: int = 14):
        self.period = period

    def name(self) -> str:
        return "RSI"

    def _calc_rsi(self, closes):
        """Returns RSI value from oldest-first closes array."""
        changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        avg_gain = sum(max(0, c) for c in changes[:self.period]) / self.period
        avg_loss = sum(abs(min(0, c)) for c in changes[:self.period]) / self.period
        for c in changes[self.period:]:
            avg_gain = (avg_gain * (self.period - 1) + max(0, c)) / self.period
            avg_loss = (avg_loss * (self.period - 1) + abs(min(0, c))) / self.period
        return 100.0 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))

    def score(self, df: pd.DataFrame) -> int:
        needed = self.period + 6  # enough for divergence look-back
        if len(df) < needed:
            return 0

        closes = df["close"].values[::-1]  # oldest first

        rsi_now = self._calc_rsi(closes)

        # Base score from RSI level
        if rsi_now < 30:
            base = 2
        elif rsi_now < 45:
            base = 1
        elif rsi_now > 70:
            base = -2
        elif rsi_now > 55:
            base = -1
        else:
            base = 0

        # Divergence: compare price and RSI over last 5 bars
        # Uses 5 windows separated by 1 bar each (looks back ~5 days)
        lookback = 5
        if len(closes) >= self.period + lookback + 2:
            rsi_prev = self._calc_rsi(closes[:-lookback])
            price_now  = closes[-1]
            price_prev = closes[-(lookback + 1)]

            price_fell = price_now < price_prev
            price_rose = price_now > price_prev
            rsi_rose   = rsi_now > rsi_prev
            rsi_fell   = rsi_now < rsi_prev

            # Bullish divergence: price lower low but RSI higher low
            if price_fell and rsi_rose and rsi_now < 50:
                base = min(base + 1, 2)

            # Bearish divergence: price higher high but RSI lower high
            if price_rose and rsi_fell and rsi_now > 50:
                base = max(base - 1, -2)

        return base
