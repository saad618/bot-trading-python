import pandas as pd
from strategies.base import TradingStrategy


class AdxStrategy(TradingStrategy):
    """
    Average Directional Index with Directional Indicators.
    ADX >= threshold AND +DI > -DI  =>  strong uptrend   (+1)
    ADX >= threshold AND -DI > +DI  =>  strong downtrend (-1)
    ADX <  threshold                =>  ranging market    (0)
    """

    def __init__(self, period: int = 14, threshold: float = 25.0):
        self.period = period
        self.threshold = threshold

    def name(self) -> str:
        return "ADX"

    def score(self, df: pd.DataFrame) -> int:
        if len(df) < self.period * 2 + 2:
            return 0

        # Use up to period*3 bars, flip to oldest-first for sequential calc
        bars = df.iloc[: self.period * 3].iloc[::-1].reset_index(drop=True)

        plus_dm_vals, minus_dm_vals, tr_vals = [], [], []
        for i in range(1, len(bars)):
            up   = bars["high"].iloc[i] - bars["high"].iloc[i - 1]
            down = bars["low"].iloc[i - 1] - bars["low"].iloc[i]
            plus_dm_vals.append(up   if up   > down and up   > 0 else 0.0)
            minus_dm_vals.append(down if down > up   and down > 0 else 0.0)
            h, l, cp = bars["high"].iloc[i], bars["low"].iloc[i], bars["close"].iloc[i - 1]
            tr_vals.append(max(h - l, abs(h - cp), abs(l - cp)))

        def wilder_smooth(vals):
            if len(vals) < self.period:
                return []
            s = [sum(vals[: self.period])]
            for v in vals[self.period :]:
                s.append(s[-1] - s[-1] / self.period + v)
            return s

        sth  = wilder_smooth(tr_vals)
        spdm = wilder_smooth(plus_dm_vals)
        smdm = wilder_smooth(minus_dm_vals)

        if not sth:
            return 0

        dx_vals = []
        for t, p, m in zip(sth, spdm, smdm):
            if t == 0:
                dx_vals.append(0.0)
                continue
            pdi   = 100 * p / t
            mdi   = 100 * m / t
            total = pdi + mdi
            dx_vals.append(0.0 if total == 0 else 100 * abs(pdi - mdi) / total)

        adx_vals = wilder_smooth(dx_vals)
        if not adx_vals:
            return 0

        adx    = adx_vals[-1]
        last_t = sth[-1]
        if last_t == 0 or adx < self.threshold:
            return 0

        plus_di  = 100 * spdm[-1] / last_t
        minus_di = 100 * smdm[-1] / last_t
        return 1 if plus_di > minus_di else -1
