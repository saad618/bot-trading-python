import time
import logging
from datetime import datetime, date
from sqlalchemy.orm import Session
from models import Trade, OpenPosition, TradeType, PositionStatus
from services import alpha_vantage
from services import atr as atr_service
from services import risk_manager
from services.portfolio import portfolio_service
from strategies import composite
from services import telegram
from config import settings

logger = logging.getLogger(__name__)
_running = True

def is_running() -> bool:
    return _running

def start():
    global _running
    _running = True
    logger.info("Trading bot started")

def stop():
    global _running
    _running = False
    logger.info("Trading bot stopped")

def execute_trading_cycle(db: Session):
    if not _running:
        logger.info("Bot paused. Skipping cycle.")
        return

    if _daily_limit_breached(db):
        logger.warning("=== CIRCUIT BREAKER: Daily loss limit reached. No new trades. ===")
        telegram.notify_circuit_breaker(get_today_pnl(db))
        return

    logger.info(f"=== Cycle Started | Cash: ₹{portfolio_service.get_cash_balance():.2f} ===")

    for i, symbol in enumerate(settings.SYMBOLS):
        try:
            _process_symbol(symbol, db)
            if i < len(settings.SYMBOLS) - 1:
                time.sleep(13)
        except Exception as e:
            logger.error(f"[{symbol}] Error: {e}")

    open_count = db.query(OpenPosition).filter(OpenPosition.status == PositionStatus.OPEN).count()
    logger.info(f"=== Cycle Done | Cash: ₹{portfolio_service.get_cash_balance():.2f} | Open: {open_count} | Today P&L: ₹{get_today_pnl(db):.2f} ===")

def _process_symbol(symbol: str, db: Session):
    df = alpha_vantage.get_daily_prices(symbol)
    if df.empty:
        logger.warning(f"[{symbol}] No data. Skipping.")
        return

    current_price = df.iloc[0]["close"]
    atr = atr_service.calculate(df)
    _check_open_positions(symbol, current_price, atr, db)

    result = composite.evaluate(df)
    breakdown = "  ".join(f"{k}:{'+' if v >= 0 else ''}{v}" for k, v in result.breakdown.items())
    logger.info(f"[{symbol}] ₹{current_price:.2f} | {breakdown} | Score:{result.score} | {result.signal} | ATR:{atr:.2f}")

    has_open = db.query(OpenPosition).filter(
        OpenPosition.symbol == symbol,
        OpenPosition.status == PositionStatus.OPEN
    ).first() is not None

    if result.signal == "BUY" and not has_open:
        _execute_buy(symbol, current_price, atr, db)
    elif result.signal == "SELL" and has_open:
        _close_by_signal(symbol, current_price, db)
    else:
        logger.info(f"[{symbol}] HOLD")

def _check_open_positions(symbol: str, price: float, atr: float, db: Session):
    positions = db.query(OpenPosition).filter(
        OpenPosition.symbol == symbol,
        OpenPosition.status == PositionStatus.OPEN
    ).all()

    for pos in positions:
        new_stop = risk_manager.calculate_trailing_stop(price, pos.stop_loss_price, atr)
        if new_stop > pos.stop_loss_price:
            logger.info(f"[{symbol}] Trailing stop: ₹{pos.stop_loss_price:.2f} → ₹{new_stop:.2f}")
            pos.stop_loss_price = new_stop
            db.commit()

        if price <= pos.stop_loss_price:
            loss = (price - pos.entry_price) * pos.quantity
            logger.warning(f"[{symbol}] STOP-LOSS hit @ ₹{price:.2f}")
            telegram.notify_stop_loss(symbol, price, abs(loss))
            _close_position(pos, price, PositionStatus.CLOSED_STOP_LOSS, db)
        elif price >= pos.target_price:
            profit = (price - pos.entry_price) * pos.quantity
            logger.info(f"[{symbol}] TARGET hit @ ₹{price:.2f}")
            telegram.notify_target(symbol, price, profit)
            _close_position(pos, price, PositionStatus.CLOSED_TARGET, db)

def _execute_buy(symbol: str, price: float, atr: float, db: Session):
    cash = portfolio_service.get_cash_balance()
    qty = risk_manager.calculate_quantity(cash, price)

    if not portfolio_service.can_buy(qty, price):
        logger.warning(f"[{symbol}] Insufficient cash")
        return

    stop_loss = risk_manager.calculate_stop_loss(price, atr)
    target = risk_manager.calculate_target(price, atr)
    mode = "PAPER TRADE" if settings.PAPER_TRADING else "LIVE TRADE"

    db.add(Trade(symbol=symbol, type=TradeType.BUY, quantity=qty, price=price,
                 total_value=qty * price, realized_pnl=0.0, notes=mode))
    db.add(OpenPosition(symbol=symbol, quantity=qty, entry_price=price,
                        stop_loss_price=stop_loss, target_price=target,
                        status=PositionStatus.OPEN))
    db.commit()
    portfolio_service.apply_trade("BUY", symbol, qty, price)
    logger.info(f"[{symbol}] BUY {qty} @ ₹{price:.2f} | SL:₹{stop_loss:.2f} | Target:₹{target:.2f}")
    telegram.notify_buy(symbol, price, stop_loss, target, qty)

def _close_by_signal(symbol: str, price: float, db: Session):
    positions = db.query(OpenPosition).filter(
        OpenPosition.symbol == symbol, OpenPosition.status == PositionStatus.OPEN
    ).all()
    for pos in positions:
        _close_position(pos, price, PositionStatus.CLOSED_SIGNAL, db)

def _close_position(pos: OpenPosition, price: float, reason: PositionStatus, db: Session):
    pnl = (price - pos.entry_price) * pos.quantity
    mode = "PAPER TRADE" if settings.PAPER_TRADING else "LIVE TRADE"

    db.add(Trade(symbol=pos.symbol, type=TradeType.SELL, quantity=pos.quantity,
                 price=price, total_value=pos.quantity * price, realized_pnl=pnl,
                 notes=f"{reason.value} | {mode}"))
    pos.status = reason
    db.commit()
    portfolio_service.apply_trade("SELL", pos.symbol, pos.quantity, price)
    logger.info(f"[{pos.symbol}] SELL {pos.quantity} @ ₹{price:.2f} | P&L:{'+' if pnl >= 0 else ''}₹{pnl:.2f} | {reason.value}")
    if reason == PositionStatus.CLOSED_SIGNAL:
        telegram.notify_sell(pos.symbol, price, pnl, "Signal")

def _daily_limit_breached(db: Session) -> bool:
    max_loss = settings.INITIAL_BALANCE * (settings.MAX_DAILY_LOSS_PERCENT / 100.0)
    return get_today_pnl(db) < -max_loss

def get_all_trades(db: Session):
    return db.query(Trade).order_by(Trade.executed_at.desc()).all()

def get_trades_by_symbol(symbol: str, db: Session):
    return db.query(Trade).filter(Trade.symbol == symbol).order_by(Trade.executed_at.desc()).all()

def get_open_positions(db: Session):
    return db.query(OpenPosition).filter(OpenPosition.status == PositionStatus.OPEN).all()

def get_total_pnl(db: Session) -> float:
    return sum(t.realized_pnl for t in db.query(Trade).all())

def get_today_pnl(db: Session) -> float:
    start = datetime.combine(date.today(), datetime.min.time())
    return sum(t.realized_pnl for t in db.query(Trade).filter(Trade.executed_at >= start).all())

def get_today_trades(db: Session):
    start = datetime.combine(date.today(), datetime.min.time())
    return db.query(Trade).filter(Trade.executed_at >= start).all()
