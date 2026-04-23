import pandas as pd
from strategies.base import TradingStrategy

class StochasticStrategy(TradingStrategy):
    """
    Stochastic Oscillator — measures where price closed relative to its range.
    %K < 20 = oversold (BUY), %K > 80 = overbought (SELL)
    """
    def __init__(self, k_period=14, d_period=3):
        self.k_period = k_period
        self.d_period = d_period

    def name(self) -> str:
        return "STOCH"

    def score(self, df: pd.DataFrame) -> int:
        if len(df) < self.k_period + self.d_period:
            return 0

        df = df.iloc[:self.k_period + self.d_period]

        k_values = []
        for i in range(self.d_period):
            window = df.iloc[i: i + self.k_period]
            low14  = window["low"].min()
            high14 = window["high"].max()
            close  = df.iloc[i]["close"]
            if high14 == low14:
                k_values.append(50.0)
            else:
                k_values.append((close - low14) / (high14 - low14) * 100)

        k = k_values[0]   # most recent %K
        d = sum(k_values) / len(k_values)  # %D (smoothed)

        if k < 20 and d < 20:
            return 1   # oversold
        if k > 80 and d > 80:
            return -1  # overbought
        return 0
