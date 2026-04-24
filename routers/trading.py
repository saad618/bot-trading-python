import threading
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from database import get_db
from services.portfolio import portfolio_service
import services.trading as trading_svc
import scheduler as sched
import backtest as bt

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
