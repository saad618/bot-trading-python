import pandas as pd
from strategies.base import TradingStrategy

class MacdStrategy(TradingStrategy):
    def __init__(self, fast=12, slow=26, signal=9):
        self.fast = fast
        self.slow = slow
        self.signal = signal

    def name(self) -> str:
        return "MACD"

    def score(self, df: pd.DataFrame) -> int:
        if len(df) < self.slow + self.signal + 2:
            return 0

        prices = df["close"].values[::-1]  # oldest first

        def ema(data, period):
            k = 2.0 / (period + 1)
            e = data[0]
            result = [e]
            for p in data[1:]:
                e = p * k + e * (1 - k)
                result.append(e)
            return result

        fast_ema  = ema(prices, self.fast)
        slow_ema  = ema(prices, self.slow)
        macd_line = [f - s for f, s in zip(fast_ema, slow_ema)]
        signal_line = ema(macd_line[self.slow:], self.signal)

        if len(signal_line) < 2:
            return 0

        macd_today  = macd_line[-(1)]
        macd_yest   = macd_line[-(2)]
        sig_today   = signal_line[-1]
        sig_yest    = signal_line[-2]

        # Bullish crossover: MACD crosses above signal
        if macd_yest <= sig_yest and macd_today > sig_today:
            return 2
        # Bearish crossover: MACD crosses below signal
        if macd_yest >= sig_yest and macd_today < sig_today:
            return -2
        # MACD above signal (bullish momentum)
        if macd_today > sig_today:
            return 1
        # MACD below signal (bearish momentum)
        if macd_today < sig_today:
            return -1
        return 0
