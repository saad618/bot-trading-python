import pandas as pd

def calculate(df: pd.DataFrame, period: int = 14) -> float:
    if len(df) < period + 1:
        return 0.0

    df = df.sort_values("date", ascending=True).reset_index(drop=True)

    tr_list = []
    for i in range(1, len(df)):
        high, low, prev_close = df.loc[i, "high"], df.loc[i, "low"], df.loc[i - 1, "close"]
        tr_list.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))

    if len(tr_list) < period:
        return 0.0

    atr = sum(tr_list[:period]) / period
    for tr in tr_list[period:]:
        atr = (atr * (period - 1) + tr) / period

    return round(atr, 2)
