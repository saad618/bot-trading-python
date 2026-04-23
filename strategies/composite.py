from dataclasses import dataclass, field
from typing import Dict
import pandas as pd
from config import settings
from strategies.ema_crossover import EmaCrossoverStrategy
from strategies.rsi import RsiStrategy
from strategies.breakout import BreakoutStrategy
from strategies.volume import VolumeConfirmationStrategy
from strategies.candlestick import CandlestickPatternStrategy
from strategies.trend_filter import TrendFilterStrategy

@dataclass
class StrategyResult:
    score: int
    breakdown: Dict[str, int]
    signal: str

_strategies = [
    EmaCrossoverStrategy(),
    RsiStrategy(),
    BreakoutStrategy(),
    VolumeConfirmationStrategy(),
    CandlestickPatternStrategy(),
    TrendFilterStrategy(),
]

def evaluate(df: pd.DataFrame) -> StrategyResult:
    breakdown = {}
    total = 0
    for s in _strategies:
        v = s.score(df)
        breakdown[s.name()] = v
        total += v

    if total >= settings.BUY_SCORE_THRESHOLD:
        signal = "BUY"
    elif total <= settings.SELL_SCORE_THRESHOLD:
        signal = "SELL"
    else:
        signal = "HOLD"

    return StrategyResult(score=total, breakdown=breakdown, signal=signal)
