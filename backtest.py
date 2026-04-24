import time
import logging
import requests
import numpy as np
import pandas as pd
from config import settings
from services import atr as atr_svc, risk_manager
from strategies import composite

logger = logging.getLogger(__name__)

# Cache: {symbol: (fetched_at_timestamp, dataframe)}
_data_cache: dict = {}
_CACHE_TTL_SECONDS = 6 * 3600  # refresh every 6 hours

# ─────────────────────────────────────────────────────────────
# Data fetching — Alpha Vantage compact (100 bars, free tier)
# ─────────────────────────────────────────────────────────────

def _fetch_full_history(symbol: str) -> pd.DataFrame:
    cached_at, cached_df = _data_cache.get(symbol, (0, pd.DataFrame()))
    if not cached_df.empty and (time.time() - cached_at) < _CACHE_TTL_SECONDS:
        logger.info(f"[{symbol}] Using cached data ({len(cached_df)} bars)")
        return cached_df

    if settings.DATA_SOURCE == "crypto":
        return _fetch_binance(symbol)
    return _fetch_alpha_vantage(symbol)

def _fetch_binance(symbol: str) -> pd.DataFrame:
    from services import binance as binance_svc
    try:
        logger.info(f"[{symbol}] Fetching from Binance...")
        df = binance_svc.get_daily_prices(symbol)   # newest-first
        if df.empty:
            return pd.DataFrame()
        df = df.sort_values("date", ascending=True).reset_index(drop=True)  # oldest-first for backtest
        _data_cache[symbol] = (time.time(), df)
        logger.info(f"[{symbol}] Fetched {len(df)} days from Binance")
        return df
    except Exception as e:
        logger.error(f"[{symbol}] Binance fetch error: {e}", exc_info=True)
        return pd.DataFrame()

def _fetch_alpha_vantage(symbol: str) -> pd.DataFrame:
    try:
        logger.info(f"[{symbol}] Fetching from Alpha Vantage (compact)...")
        params = {
            "function":   "TIME_SERIES_DAILY",
            "symbol":     symbol,
            "outputsize": "compact",
            "apikey":     settings.BACKTEST_API_KEY,
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
        _data_cache[symbol] = (time.time(), df)
        return df

    except Exception as e:
        logger.error(f"[{symbol}] Fetch error: {e}", exc_info=True)
        return pd.DataFrame()

# ─────────────────────────────────────────────────────────────
# Single-symbol simulation
# ─────────────────────────────────────────────────────────────

def _simulate(symbol: str, df: pd.DataFrame, capital: float, buy_threshold: int = None, sell_threshold: int = None) -> dict:
    trades = []
    cash = capital
    position = None
    WARMUP = 60
    max_score = -99
    min_score = 99
    score_samples = []
    buy_opportunities = 0
    buy_failed_qty = 0

    for i in range(WARMUP, len(df)):
        window = df.iloc[:i + 1].sort_values("date", ascending=False).reset_index(drop=True)
        today = df.iloc[i]
        price = today["close"]
        atr = atr_svc.calculate(window)

        if position:
            # Breakeven: once price reaches halfway to target, lock stop at entry
            halfway = position["entry"] + (position["target"] - position["entry"]) * 0.5
            if price >= halfway and position["stop"] < position["entry"]:
                position["stop"] = position["entry"]

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
        if result.score > max_score:
            max_score = result.score
        if result.score < min_score:
            min_score = result.score
        if len(score_samples) < 5:
            score_samples.append({"date": str(today["date"].date()), "score": result.score, "breakdown": result.breakdown})

        buy_thr  = buy_threshold  if buy_threshold  is not None else settings.BUY_SCORE_THRESHOLD
        sell_thr = sell_threshold if sell_threshold is not None else settings.SELL_SCORE_THRESHOLD

        if result.score >= buy_thr and position is None:
            if settings.DISABLE_TREND_FILTER:
                in_uptrend = True
            else:
                prices_arr = window["close"].values[::-1][:20]
                k20 = 2.0 / 21
                ema20 = float(prices_arr[0])
                for p in prices_arr[1:]:
                    ema20 = float(p) * k20 + ema20 * (1 - k20)
                in_uptrend = float(price) > ema20

            if in_uptrend:
                buy_opportunities += 1
                qty = risk_manager.calculate_quantity(cash, float(price), result.score)
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
                else:
                    buy_failed_qty += 1

        elif result.score <= sell_thr and position:
            if price > position["entry"]:  # only signal-exit profitable positions
                pnl = (price - position["entry"]) * position["qty"]
                cash += position["qty"] * price
                trades.append({"date": str(today["date"].date()), "type": "SELL",
                                "price": round(price, 2), "qty": position["qty"],
                                "pnl": round(pnl, 2), "reason": "SIGNAL"})
                position = None
            # else: let stop-loss handle the exit

    # Close open position at end of period
    if position:
        price = df.iloc[-1]["close"]
        pnl = (price - position["entry"]) * position["qty"]
        trades.append({"date": str(df.iloc[-1]["date"].date()), "type": "SELL",
                        "price": round(price, 2), "qty": position["qty"],
                        "pnl": round(pnl, 2), "reason": "END_OF_PERIOD"})

    diagnostics = {
        "buy_thr_used": buy_thr,
        "sell_thr_used": sell_thr,
        "max_score": max_score,
        "min_score": min_score,
        "buy_opportunities": buy_opportunities,
        "buy_failed_qty": buy_failed_qty,
        "score_samples": score_samples,
    }
    return {"symbol": symbol, "trades": trades, "metrics": _metrics(trades, capital), "diagnostics": diagnostics}

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

def run(lookback_days: int = 365, buy_threshold: int = None, sell_threshold: int = None) -> dict:
    symbols      = settings.SYMBOLS
    capital_each = settings.INITIAL_BALANCE / len(symbols)
    results      = []

    for i, symbol in enumerate(symbols):
        logger.info(f"Backtesting [{symbol}] ...")
        if i > 0 and settings.DATA_SOURCE == "stocks":
            time.sleep(13)  # Alpha Vantage free tier: 5 req/min

        df = _fetch_full_history(symbol)
        if df.empty:
            logger.warning(f"[{symbol}] Skipped — no data")
            continue

        cutoff = df["date"].max() - pd.Timedelta(days=lookback_days)
        df = df[df["date"] >= cutoff].reset_index(drop=True)

        if len(df) < 70:
            logger.warning(f"[{symbol}] Skipped — insufficient history ({len(df)} bars)")
            continue

        full_result = _simulate(symbol, df, capital_each, buy_threshold, sell_threshold)

        # Walk-forward: re-simulate on last 30% of bars (out-of-sample test)
        oos_start = int(len(df) * 0.7)
        df_oos = df.iloc[oos_start:].reset_index(drop=True)
        if len(df_oos) >= 70:
            oos_result = _simulate(symbol, df_oos, capital_each, buy_threshold, sell_threshold)
            full_result["oos_metrics"] = oos_result["metrics"]
        else:
            full_result["oos_metrics"] = {"note": "Insufficient data for OOS test"}

        results.append(full_result)

    # Portfolio summary (full period)
    all_pnl = [t["pnl"] for r in results for t in r["trades"] if t["type"] == "SELL"]
    wins     = [p for p in all_pnl if p > 0]

    # OOS summary (honest out-of-sample view)
    oos_total = sum(r["oos_metrics"]["total_pnl"] for r in results
                    if isinstance(r.get("oos_metrics"), dict) and "total_pnl" in r["oos_metrics"])
    oos_trades = sum(r["oos_metrics"].get("total_trades", 0) for r in results
                     if isinstance(r.get("oos_metrics"), dict))
    oos_wins   = sum(r["oos_metrics"].get("winning_trades", 0) for r in results
                     if isinstance(r.get("oos_metrics"), dict))

    summary = {
        "period_days":       lookback_days,
        "symbols_tested":    len(results),
        "total_trades":      len(all_pnl),
        "win_rate_pct":      round(len(wins) / len(all_pnl) * 100, 1) if all_pnl else 0,
        "total_pnl":         round(sum(all_pnl), 2),
        "total_return_pct":  round(sum(all_pnl) / settings.INITIAL_BALANCE * 100, 2),
        "initial_balance":   settings.INITIAL_BALANCE,
        "final_balance":     round(settings.INITIAL_BALANCE + sum(all_pnl), 2),
        "oos_summary": {
            "trades":   oos_trades,
            "win_rate": round(oos_wins / oos_trades * 100, 1) if oos_trades else 0,
            "total_pnl": round(oos_total, 2),
            "note": "Last 30% of data — honest out-of-sample performance",
        },
    }

    return {"summary": summary, "per_symbol": results}
