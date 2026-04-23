import requests
import pandas as pd
import logging
from config import settings

logger = logging.getLogger(__name__)

def get_daily_prices(symbol: str) -> pd.DataFrame:
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
            return pd.DataFrame()

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

        return pd.DataFrame(records).sort_values("date", ascending=False).reset_index(drop=True)

    except Exception as e:
        logger.error(f"[{symbol}] Error fetching prices: {e}")
        return pd.DataFrame()
