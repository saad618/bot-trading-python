import pandas as pd
from strategies.base import TradingStrategy

class VolumeConfirmationStrategy(TradingStrategy):
    def name(self) -> str:
        return "VOL"

    def score(self, df: pd.DataFrame) -> int:
        if len(df) < 21:
            return 0

        today = df.iloc[0]
        avg_volume = df.iloc[1:21]["volume"].mean()

        if today["volume"] > avg_volume * 1.5:
            return 1 if today["close"] >= today["open"] else -1
        return 0
