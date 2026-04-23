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
    from config import settings
    api_key = os.getenv("BACKTEST_API_KEY", settings.API_KEY)
    api_key = api_key.strip().lstrip("=").strip()
    results = {}
    # Test compact
    try:
        params = {"function": "TIME_SERIES_DAILY", "symbol": "RELIANCE.BSE",
                  "outputsize": "compact", "apikey": api_key}
        data = requests.get(settings.API_BASE_URL, params=params, timeout=15).json()
        results["compact"] = {"rows": len(data.get("Time Series (Daily)", {})),
                               "keys": list(data.keys())}
    except Exception as e:
        results["compact"] = {"error": str(e)}
    # Test full
    try:
        params["outputsize"] = "full"
        data = requests.get(settings.API_BASE_URL, params=params, timeout=30).json()
        results["full"] = {"rows": len(data.get("Time Series (Daily)", {})),
                           "keys": list(data.keys()),
                           "message": str(data.get("Note", data.get("Information", "ok")))}
    except Exception as e:
        results["full"] = {"error": str(e)}
    return {"api_key": api_key[:8] + "...", "results": results}

@router.post("/backtest")
def start_backtest(background_tasks: BackgroundTasks, days: int = 365):
    global _backtest_result
    if _backtest_result["status"] == "running":
        return {"status": "already running — check /api/backtest/result"}
    _backtest_result = {"status": "running", "result": None}

    def _run():
        global _backtest_result
        try:
            result = bt.run(lookback_days=days)
            _backtest_result = {"status": "done", "result": result}
        except Exception as e:
            _backtest_result = {"status": "error", "result": str(e)}

    background_tasks.add_task(_run)
    return {"status": "started", "message": f"Backtesting {days} days — takes ~65 seconds. Poll /api/backtest/result"}

@router.get("/backtest/result")
def get_backtest_result():
    return _backtest_result
