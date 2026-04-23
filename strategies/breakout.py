import pandas as pd
from strategies.base import TradingStrategy

class BreakoutStrategy(TradingStrategy):
    def __init__(self, period: int = 20):
        self.period = period

    def name(self) -> str:
        return "BRK"

    def score(self, df: pd.DataFrame) -> int:
        if len(df) < self.period + 1:
            return 0

        current_price = df.iloc[0]["close"]
        past = df.iloc[1:self.period + 1]

        if current_price > past["high"].max():
            return 1
        if current_price < past["low"].min():
            return -1
        return 0
