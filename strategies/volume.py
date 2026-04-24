import pandas as pd
from strategies.base import TradingStrategy


class VolumeConfirmationStrategy(TradingStrategy):
    def name(self) -> str:
        return "VOL"

    def score(self, df: pd.DataFrame) -> int:
        if len(df) < 21:
            return 0

        today     = df.iloc[0]
        avg_vol   = df.iloc[1:21]["volume"].mean()
        if avg_vol == 0:
            return 0

        ratio     = float(today["volume"]) / float(avg_vol)
        bullish   = float(today["close"]) >= float(today["open"])

        # Strong volume spike — high conviction candle
        if ratio >= 2.0:
            return 1 if bullish else -1

        # Moderate spike — mild confirmation
        if ratio >= 1.2:
            return 1 if bullish else -1

        # Volume drying up — weakening move, slight negative signal
        if ratio < 0.6:
            return -1 if bullish else 1

        return 0
