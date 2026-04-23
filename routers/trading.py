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
    import requests, os
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY", "T50H37RBFKT509FY")
    try:
        params = {
            "function": "TIME_SERIES_DAILY", "symbol": "RELIANCE.BSE",
            "outputsize": "compact", "apikey": api_key, "datatype": "json",
        }
        data = requests.get("https://www.alphavantage.co/query", params=params, timeout=30).json()
        if "Error Message" in data:
            return {"status": "failed", "message": data["Error Message"]}
        if "Information" in data:
            return {"status": "rate_limited", "message": data["Information"]}
        ts = data.get("Time Series (Daily)", {})
        if not ts:
            return {"status": "failed", "message": "No time series data", "keys": list(data.keys())}
        rows = list(ts.items())
        return {"status": "ok", "source": "Alpha Vantage (compact)", "rows": len(rows), "latest_date": rows[0][0], "sample": rows[0][1]}
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
