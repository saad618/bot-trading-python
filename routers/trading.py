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
    import requests, pandas as pd
    from io import StringIO
    try:
        end   = pd.Timestamp.today().strftime("%Y%m%d")
        start = (pd.Timestamp.today() - pd.Timedelta(days=60)).strftime("%Y%m%d")
        url   = f"https://stooq.com/q/d/l/?s=reliance.bo&d1={start}&d2={end}&i=d"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        r = requests.get(url, headers=headers, timeout=30)
        text = r.text.strip()
        if r.status_code != 200 or "No data" in text or len(text.splitlines()) < 3:
            return {"status": "failed", "http": r.status_code, "body": text[:300]}
        df = pd.read_csv(StringIO(text))
        rows = df.to_dict(orient="records")
        return {"status": "ok", "source": "Stooq (free)", "rows": len(rows), "sample": rows[-1] if rows else None}
    except Exception as e:
        return {"status": "error", "error": str(e)}

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
