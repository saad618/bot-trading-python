import time
import logging
import requests
import numpy as np
import pandas as pd
from config import settings
from services import atr as atr_svc, risk_manager
from strategies import composite

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Data fetching — Alpha Vantage compact (100 bars, free tier)
# ─────────────────────────────────────────────────────────────

def _fetch_full_history(symbol: str) -> pd.DataFrame:
    try:
        logger.info(f"[{symbol}] Fetching from Alpha Vantage (compact)...")
        params = {
            "function":   "TIME_SERIES_DAILY",
            "symbol":     symbol,
            "outputsize": "compact",
            "apikey":     settings.API_KEY,
            "datatype":   "json",
        }
        r = requests.get(settings.API_BASE_URL, params=params, timeout=30)
        data = r.json()

        if "Error Message" in data:
            logger.warning(f"[{symbol}] Alpha Vantage error: {data['Error Message']}")
            return pd.DataFrame()
        if "Information" in data:
            logger.warning(f"[{symbol}] Alpha Vantage rate limit: {data['Information']}")
            return pd.DataFrame()

        ts = data.get("Time Series (Daily)", {})
        if not ts:
            logger.warning(f"[{symbol}] No time series data returned")
            return pd.DataFrame()

        records = [
            {
                "date":   pd.to_datetime(date),
                "open":   float(v["1. open"]),
                "high":   float(v["2. high"]),
                "low":    float(v["3. low"]),
                "close":  float(v["4. close"]),
                "volume": float(v["5. volume"]),
            }
            for date, v in ts.items()
        ]
        df = pd.DataFrame(records).sort_values("date", ascending=True).reset_index(drop=True)
        logger.info(f"[{symbol}] Fetched {len(df)} days from Alpha Vantage")
        return df

    except Exception as e:
        logger.error(f"[{symbol}] Fetch error: {e}", exc_info=True)
        return pd.DataFrame()

# ─────────────────────────────────────────────────────────────
# Single-symbol simulation
# ─────────────────────────────────────────────────────────────

def _simulate(symbol: str, df: pd.DataFrame, capital: float) -> dict:
    trades = []
    cash = capital
    position = None
    WARMUP = 60

    for i in range(WARMUP, len(df)):
        window = df.iloc[:i + 1].sort_values("date", ascending=False).reset_index(drop=True)
        today = df.iloc[i]
        price = today["close"]
        atr = atr_svc.calculate(window)

        if position:
            # Raise trailing stop
            new_stop = risk_manager.calculate_trailing_stop(price, position["stop"], atr)
            if new_stop > position["stop"]:
                position["stop"] = new_stop

            # Stop-loss hit
            if price <= position["stop"]:
                pnl = (price - position["entry"]) * position["qty"]
                cash += position["qty"] * price
                trades.append({"date": str(today["date"].date()), "type": "SELL",
                                "price": round(price, 2), "qty": position["qty"],
                                "pnl": round(pnl, 2), "reason": "STOP_LOSS"})
                position = None
                continue

            # Target hit
            if price >= position["target"]:
                pnl = (price - position["entry"]) * position["qty"]
                cash += position["qty"] * price
                trades.append({"date": str(today["date"].date()), "type": "SELL",
                                "price": round(price, 2), "qty": position["qty"],
                                "pnl": round(pnl, 2), "reason": "TARGET"})
                position = None
                continue

        result = composite.evaluate(window)

        if result.signal == "BUY" and position is None:
            qty = risk_manager.calculate_quantity(cash, price)
            if qty > 0 and cash >= qty * price:
                cash -= qty * price
                position = {
                    "qty":    qty,
                    "entry":  price,
                    "stop":   risk_manager.calculate_stop_loss(price, atr),
                    "target": risk_manager.calculate_target(price, atr),
                }
                trades.append({"date": str(today["date"].date()), "type": "BUY",
                                "price": round(price, 2), "qty": qty, "pnl": 0, "reason": "SIGNAL"})

        elif result.signal == "SELL" and position:
            pnl = (price - position["entry"]) * position["qty"]
            cash += position["qty"] * price
            trades.append({"date": str(today["date"].date()), "type": "SELL",
                            "price": round(price, 2), "qty": position["qty"],
                            "pnl": round(pnl, 2), "reason": "SIGNAL"})
            position = None

    # Close open position at end of period
    if position:
        price = df.iloc[-1]["close"]
        pnl = (price - position["entry"]) * position["qty"]
        trades.append({"date": str(df.iloc[-1]["date"].date()), "type": "SELL",
                        "price": round(price, 2), "qty": position["qty"],
                        "pnl": round(pnl, 2), "reason": "END_OF_PERIOD"})

    return {"symbol": symbol, "trades": trades, "metrics": _metrics(trades, capital)}

# ─────────────────────────────────────────────────────────────
# Metrics calculation
# ─────────────────────────────────────────────────────────────

def _metrics(trades: list, capital: float) -> dict:
    sells = [t for t in trades if t["type"] == "SELL"]
    if not sells:
        return {"total_trades": 0, "note": "No completed trades in this period"}

    pnls = [t["pnl"] for t in sells]
    wins  = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    total_pnl = sum(pnls)
    win_rate  = round(len(wins) / len(sells) * 100, 1)

    # Max drawdown
    equity = capital
    peak   = capital
    max_dd = 0.0
    for p in pnls:
        equity += p
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak * 100
        if dd > max_dd:
            max_dd = dd

    # Sharpe ratio (annualised, rough)
    if len(pnls) > 1:
        returns = [p / capital for p in pnls]
        sharpe = round((np.mean(returns) / (np.std(returns) + 1e-9)) * np.sqrt(252), 2)
    else:
        sharpe = 0.0

    by_reason = {}
    for t in sells:
        r = t["reason"]
        by_reason[r] = by_reason.get(r, 0) + 1

    return {
        "total_trades":      len(sells),
        "winning_trades":    len(wins),
        "losing_trades":     len(losses),
        "win_rate_pct":      win_rate,
        "total_pnl":         round(total_pnl, 2),
        "total_return_pct":  round(total_pnl / capital * 100, 2),
        "avg_win":           round(np.mean(wins),   2) if wins   else 0,
        "avg_loss":          round(np.mean(losses), 2) if losses else 0,
        "best_trade":        round(max(pnls), 2),
        "worst_trade":       round(min(pnls), 2),
        "max_drawdown_pct":  round(max_dd, 2),
        "sharpe_ratio":      sharpe,
        "exits_by_reason":   by_reason,
    }

# ─────────────────────────────────────────────────────────────
# Full portfolio backtest
# ─────────────────────────────────────────────────────────────

def run(lookback_days: int = 365) -> dict:
    symbols      = settings.SYMBOLS
    capital_each = settings.INITIAL_BALANCE / len(symbols)
    results      = []

    for i, symbol in enumerate(symbols):
        logger.info(f"Backtesting [{symbol}] ...")
        if i > 0:
            time.sleep(13)  # Alpha Vantage 5 req/min

        df = _fetch_full_history(symbol)
        if df.empty:
            logger.warning(f"[{symbol}] Skipped — no data")
            continue

        cutoff = df["date"].max() - pd.Timedelta(days=lookback_days)
        df = df[df["date"] >= cutoff].reset_index(drop=True)

        if len(df) < 80:
            logger.warning(f"[{symbol}] Skipped — insufficient history")
            continue

        results.append(_simulate(symbol, df, capital_each))

    # Portfolio summary
    all_pnl = [t["pnl"] for r in results for t in r["trades"] if t["type"] == "SELL"]
    wins     = [p for p in all_pnl if p > 0]

    summary = {
        "period_days":       lookback_days,
        "symbols_tested":    len(results),
        "total_trades":      len(all_pnl),
        "win_rate_pct":      round(len(wins) / len(all_pnl) * 100, 1) if all_pnl else 0,
        "total_pnl":         round(sum(all_pnl), 2),
        "total_return_pct":  round(sum(all_pnl) / settings.INITIAL_BALANCE * 100, 2),
        "initial_balance":   settings.INITIAL_BALANCE,
        "final_balance":     round(settings.INITIAL_BALANCE + sum(all_pnl), 2),
    }

    return {"summary": summary, "per_symbol": results}
