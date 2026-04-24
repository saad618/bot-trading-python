import pandas as pd
import numpy as np
from strategies.base import TradingStrategy

class BollingerBandsStrategy(TradingStrategy):
    def __init__(self, period=20, std_dev=2.0):
        self.period = period
        self.std_dev = std_dev

    def name(self) -> str:
        return "BB"

    def score(self, df: pd.DataFrame) -> int:
        # Need extra history to detect squeeze (compare current width to avg width)
        if len(df) < self.period * 2:
            return 0

        closes = df["close"].values  # newest first

        def _band_width(window):
            m = window.mean()
            s = window.std()
            return (self.std_dev * s * 2) / m if m != 0 else 0  # width as % of mid

        current_window = closes[:self.period]
        middle = current_window.mean()
        std    = current_window.std()
        upper  = middle + self.std_dev * std
        lower  = middle - self.std_dev * std
        price  = float(closes[0])

        current_width = _band_width(current_window)

        # Historical average band width over prior period bars
        hist_window = closes[self.period:self.period * 2]
        avg_width   = _band_width(hist_window)

        squeeze = avg_width > 0 and current_width < avg_width * 0.75

        # Breakout from squeeze — strong signal
        if squeeze:
            if price >= upper:
                return 1   # breakout upward from compressed bands
            if price <= lower:
                return -1  # breakout downward from compressed bands

        # Standard band position scoring
        if price <= lower:
            return 1   # oversold — potential bounce
        if price >= upper:
            return -1  # overbought — potential drop

        return 0
