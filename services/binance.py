import time
import requests
import pandas as pd
import logging

logger = logging.getLogger(__name__)

_cache: dict = {}
_CACHE_TTL = 1 * 3600        # 1-hour cache (crypto moves faster than stocks)
_BASE_URL   = "https://api.binance.com/api/v3/klines"

def _to_binance_symbol(symbol: str) -> str:
    """'BTC/USDT' or 'btcusdt' → 'BTCUSDT'"""
    return symbol.replace("/", "").upper()

def get_daily_prices(symbol: str) -> pd.DataFrame:
    """
    Returns daily OHLCV DataFrame, newest row first — same contract as alpha_vantage.
    No API key required (public endpoint).
    """
    cached_at, cached_df = _cache.get(symbol, (0, pd.DataFrame()))
    if not cached_df.empty and (time.time() - cached_at) < _CACHE_TTL:
        return cached_df

    try:
        params = {
            "symbol":   _to_binance_symbol(symbol),
            "interval": "1d",
            "limit":    1000,  # ~2.7 years of daily candles (Binance max)
        }
        r = requests.get(_BASE_URL, params=params, timeout=30)
        r.raise_for_status()
        raw = r.json()

        if not raw or isinstance(raw, dict):
            logger.warning(f"[{symbol}] Unexpected Binance response: {raw}")
            return cached_df

        records = [
            {
                "date":   pd.to_datetime(candle[0], unit="ms"),
                "open":   float(candle[1]),
                "high":   float(candle[2]),
                "low":    float(candle[3]),
                "close":  float(candle[4]),
                "volume": float(candle[5]),
            }
            for candle in raw
        ]

        # Newest first — matches alpha_vantage contract
        df = pd.DataFrame(records).sort_values("date", ascending=False).reset_index(drop=True)
        _cache[symbol] = (time.time(), df)
        logger.info(f"[{symbol}] Fetched {len(df)} bars from Binance (cached 1h)")
        return df

    except Exception as e:
        logger.error(f"[{symbol}] Binance fetch error: {e}")
        return cached_df   # return stale rather than nothing
