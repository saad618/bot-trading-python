from dataclasses import dataclass
from typing import Dict
import pandas as pd
from config import settings
from strategies.ema_crossover import EmaCrossoverStrategy
from strategies.rsi import RsiStrategy
from strategies.breakout import BreakoutStrategy
from strategies.volume import VolumeConfirmationStrategy
from strategies.candlestick import CandlestickPatternStrategy
from strategies.trend_filter import TrendFilterStrategy
from strategies.macd import MacdStrategy
from strategies.bollinger_bands import BollingerBandsStrategy
from strategies.stochastic import StochasticStrategy
from strategies.adx import AdxStrategy

@dataclass
class StrategyResult:
    score: int
    breakdown: Dict[str, int]
    signal: str

# All 10 strategies
# Max possible score: EMA±2 + RSI±2 + MACD±2 + ADX±1 + BRK±1 + VOL±1 + CDL±1 + TRD±1 + BB±1 + STOCH±1 = ±13
_strategies = [
    EmaCrossoverStrategy(),
    RsiStrategy(),
    MacdStrategy(),
    AdxStrategy(),
    BollingerBandsStrategy(),
    StochasticStrategy(),
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
