import pandas as pd
from strategies.base import TradingStrategy

class EmaCrossoverStrategy(TradingStrategy):
    def name(self) -> str:
        return "EMA"

    def score(self, df: pd.DataFrame) -> int:
        if len(df) < 22:
            return 0

        prices = df["close"].values[::-1]  # oldest first

        def ema_last_two(period):
            k = 2.0 / (period + 1)
            ema = prices[0]
            prev = prices[0]
            for p in prices[1:]:
                prev = ema
                ema = p * k + ema * (1 - k)
            return ema, prev

        ema9_now, ema9_prev = ema_last_two(9)
        ema21_now, ema21_prev = ema_last_two(21)

        if ema9_prev <= ema21_prev and ema9_now > ema21_now:
            return 2    # golden cross
        if ema9_prev >= ema21_prev and ema9_now < ema21_now:
            return -2   # death cross
        if ema9_now > ema21_now:
            return 1    # bullish trend continuation
        if ema9_now < ema21_now:
            return -1   # bearish trend continuation
        return 0
