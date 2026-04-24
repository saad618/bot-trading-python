import threading
from fastapi import APIRouter, Depends, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from database import get_db
from services.portfolio import portfolio_service
import services.trading as trading_svc
import scheduler as sched
import backtest as bt

class SymbolBody(BaseModel):
    symbol: str

router = APIRouter(prefix="/api")

@router.get("/trading/status")
def get_status():
    return {"running": trading_svc.is_running()}

@router.get("/config")
def get_config():
    from config import settings
    return {
        "data_source": settings.DATA_SOURCE,
        "symbols": settings.SYMBOLS,
        "stop_loss_pct": settings.STOP_LOSS_PERCENT,
        "target_pct": settings.TARGET_PERCENT,
        "max_daily_loss_pct": settings.MAX_DAILY_LOSS_PERCENT,
        "buy_threshold": settings.BUY_SCORE_THRESHOLD,
        "trend_filter": not settings.DISABLE_TREND_FILTER,
    }

@router.post("/trading/test-telegram")
def test_telegram():
    from services.telegram import send_message
    send_message(
        "✅ <b>Telegram connected!</b>\n"
        "🤖 Trading Bot is live\n"
        "📊 You will receive alerts for every trade"
    )
    return "Test message sent"

@router.post("/trading/start")
def start():
    trading_svc.start()
    return "Trading bot started"

@router.post("/trading/stop")
def stop():
    trading_svc.stop()
    return "Trading bot paused"

@router.post("/trading/execute")
def execute_now():
    threading.Thread(target=sched._run_trading_cycle, daemon=True).start()
    return "Trading cycle triggered"

@router.post("/trading/report")
def send_report():
    sched.send_daily_report()
    return "Daily report email triggered"

@router.get("/trades")
def get_all_trades(db: Session = Depends(get_db)):
    return trading_svc.get_all_trades(db)

@router.get("/trades/{symbol}")
def get_trades_by_symbol(symbol: str, db: Session = Depends(get_db)):
    return trading_svc.get_trades_by_symbol(symbol.upper(), db)

@router.get("/positions")
def get_open_positions(db: Session = Depends(get_db)):
    return trading_svc.get_open_positions(db)

@router.get("/pnl")
def get_pnl(db: Session = Depends(get_db)):
    return {
        "totalRealizedPnl": trading_svc.get_total_pnl(db),
        "openPositions": len(trading_svc.get_open_positions(db)),
        "cashBalance": portfolio_service.get_cash_balance(),
    }

@router.get("/portfolio")
def get_portfolio():
    return {
        "cashBalance": portfolio_service.get_cash_balance(),
        "holdings": portfolio_service.get_holdings(),
    }

_backtest_result = {"status": "idle", "result": None}

@router.get("/backtest/test-fetch")
def test_fetch():
    from config import settings
    symbol = settings.SYMBOLS[0]
    try:
        if settings.DATA_SOURCE == "crypto":
            from services import binance as binance_svc
            df = binance_svc.get_daily_prices(symbol)
            if df.empty:
                return {"status": "failed", "message": "No data returned from Binance"}
            return {"status": "ok", "source": "Binance", "symbol": symbol,
                    "rows": len(df), "latest_date": str(df.iloc[0]["date"].date()),
                    "latest_close": df.iloc[0]["close"]}
        else:
            import requests as req
            api_key = settings.API_KEY
            params = {"function": "TIME_SERIES_DAILY", "symbol": symbol,
                      "outputsize": "compact", "apikey": api_key, "datatype": "json"}
            data = req.get(settings.API_BASE_URL, params=params, timeout=30).json()
            if "Error Message" in data:
                return {"status": "failed", "message": data["Error Message"]}
            if "Information" in data:
                return {"status": "rate_limited", "message": data["Information"]}
            ts = data.get("Time Series (Daily)", {})
            rows = list(ts.items())
            return {"status": "ok", "source": "Alpha Vantage", "symbol": symbol,
                    "rows": len(rows), "latest_date": rows[0][0]}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@router.post("/backtest")
def start_backtest(background_tasks: BackgroundTasks, days: int = 365, buy_threshold: int = None, sell_threshold: int = None):
    global _backtest_result
    if _backtest_result["status"] == "running":
        return {"status": "already running — check /api/backtest/result"}
    _backtest_result = {"status": "running", "result": None}

    def _run():
        global _backtest_result
        try:
            result = bt.run(lookback_days=days, buy_threshold=buy_threshold, sell_threshold=sell_threshold)
            _backtest_result = {"status": "done", "result": result}
        except Exception as e:
            _backtest_result = {"status": "error", "result": str(e)}

    background_tasks.add_task(_run)
    return {"status": "started", "message": f"Backtesting {days} days (buy≥{buy_threshold or 5}, sell≤{sell_threshold or -5}) — takes ~65 seconds. Poll /api/backtest/result"}

@router.get("/backtest/result")
def get_backtest_result():
    return _backtest_result

@router.post("/backtest/clear-cache")
def clear_cache():
    bt._data_cache.clear()
    return {"status": "ok", "message": "Data cache cleared — next backtest will re-fetch from Alpha Vantage"}

@router.get("/signals")
def get_live_signals():
    """Return current strategy scores for every symbol."""
    from config import settings
    from strategies import composite
    from services import atr as atr_svc
    from services import binance as binance_svc
    from services import alpha_vantage

    results = []
    for symbol in settings.SYMBOLS:
        try:
            df = binance_svc.get_daily_prices(symbol) if settings.DATA_SOURCE == "crypto" \
                 else alpha_vantage.get_daily_prices(symbol)
            if df.empty:
                results.append({"symbol": symbol, "error": "no data"})
                continue

            result = composite.evaluate(df)
            price  = float(df.iloc[0]["close"])
            atr    = float(atr_svc.calculate(df))

            # 20-EMA uptrend check (skipped if DISABLE_TREND_FILTER=true)
            if settings.DISABLE_TREND_FILTER:
                in_uptrend = True
                ema20 = 0.0
            else:
                prices = df["close"].values[::-1][:20]
                k = 2.0 / 21
                ema20 = float(prices[0])
                for p in prices[1:]:
                    ema20 = float(p) * k + ema20 * (1 - k)
                in_uptrend = price > ema20

            results.append({
                "symbol":     symbol,
                "price":      round(price, 4),
                "score":      int(result.score),
                "signal":     result.signal,
                "in_uptrend": in_uptrend,
                "ema20":      round(ema20, 4),
                "atr":        atr,
                "breakdown":  {k: int(v) for k, v in result.breakdown.items()},
                "buy_blocked_reason": (
                    "downtrend (price < 20-EMA)" if result.signal == "BUY" and not in_uptrend
                    else "score below threshold" if result.score < settings.BUY_SCORE_THRESHOLD
                    else None
                ),
            })
        except Exception as e:
            results.append({"symbol": symbol, "error": str(e)})

    return {
        "buy_threshold":  settings.BUY_SCORE_THRESHOLD,
        "sell_threshold": settings.SELL_SCORE_THRESHOLD,
        "signals":        results,
    }

@router.get("/symbols")
def get_symbols():
    from config import settings
    return {"symbols": settings.SYMBOLS, "data_source": settings.DATA_SOURCE}

@router.post("/symbols")
def add_symbol(req: SymbolBody):
    from config import settings
    from database import set_setting
    sym = req.symbol.strip().upper()
    if not sym:
        return {"error": "Symbol cannot be empty"}
    if sym in settings.SYMBOLS:
        return {"error": f"{sym} already in list"}
    settings.SYMBOLS = settings.SYMBOLS + [sym]
    set_setting("symbols", ",".join(settings.SYMBOLS))
    return {"symbols": settings.SYMBOLS}

@router.post("/symbols/remove")
def remove_symbol(req: SymbolBody):
    from config import settings
    from database import set_setting
    sym = req.symbol.strip().upper()
    if sym not in settings.SYMBOLS:
        return {"error": f"{sym} not in list"}
    if len(settings.SYMBOLS) <= 1:
        return {"error": "Cannot remove last symbol"}
    settings.SYMBOLS = [s for s in settings.SYMBOLS if s != sym]
    set_setting("symbols", ",".join(settings.SYMBOLS))
    return {"symbols": settings.SYMBOLS}

@router.get("/ml/status")
def ml_status():
    from services import ml_model as ml
    return ml.get_status()

@router.post("/ml/retrain")
def ml_retrain(db: Session = Depends(get_db)):
    from services import ml_model as ml
    return ml.retrain(db)

@router.post("/ml/train-from-backtest")
def ml_train_from_backtest(background_tasks: BackgroundTasks, days: int = 365):
    """Run backtest silently, collect all (scores, outcome) pairs, train ML model."""
    global _backtest_result

    _bt_train_result = {"status": "running", "result": None}

    def _run():
        try:
            result = bt.run(lookback_days=days)
            samples = []
            for sym_result in result.get("per_symbol", []):
                samples.extend(sym_result.get("ml_samples", []))
            from services import ml_model as ml
            train_result = ml.train_from_samples(samples)
            _bt_train_result["status"] = "done"
            _bt_train_result["result"] = train_result
        except Exception as e:
            _bt_train_result["status"] = "error"
            _bt_train_result["result"] = str(e)

    background_tasks.add_task(_run)
    return {
        "status": "started",
        "message": f"Running {days}-day backtest to collect training data — takes ~65s. Poll /api/ml/status when done."
    }
