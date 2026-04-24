import time
import requests
import pandas as pd
import logging
from config import settings

logger = logging.getLogger(__name__)

# Cache daily OHLCV data — refreshes every 4 hours (daily data doesn't change intraday)
_cache: dict = {}
_CACHE_TTL = 4 * 3600

def get_daily_prices(symbol: str) -> pd.DataFrame:
    cached_at, cached_df = _cache.get(symbol, (0, pd.DataFrame()))
    if not cached_df.empty and (time.time() - cached_at) < _CACHE_TTL:
        return cached_df

    try:
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol,
            "outputsize": "compact",
            "apikey": settings.API_KEY
        }
        response = requests.get(settings.API_BASE_URL, params=params, timeout=30)
        data = response.json()

        if "Note" in data or "Information" in data:
            logger.warning(f"[{symbol}] Rate limit hit")
            return cached_df  # return stale data rather than nothing

        time_series = data.get("Time Series (Daily)", {})
        if not time_series:
            logger.warning(f"[{symbol}] No price data returned")
            return pd.DataFrame()

        records = [
            {
                "date": pd.to_datetime(date_str),
                "open": float(v["1. open"]),
                "high": float(v["2. high"]),
                "low": float(v["3. low"]),
                "close": float(v["4. close"]),
                "volume": float(v["5. volume"]),
            }
            for date_str, v in time_series.items()
        ]

        df = pd.DataFrame(records).sort_values("date", ascending=False).reset_index(drop=True)
        _cache[symbol] = (time.time(), df)
        logger.info(f"[{symbol}] Fetched {len(df)} bars from Alpha Vantage (cached for 4h)")
        return df

    except Exception as e:
        logger.error(f"[{symbol}] Error fetching prices: {e}")
        return cached_df  # return stale data on error rather than nothing
