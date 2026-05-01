import json
import time
import logging
from collections import deque
from datetime import datetime, date
from sqlalchemy.orm import Session
from models import Trade, OpenPosition, TradeType, PositionStatus
from services import alpha_vantage
from services import binance as binance_svc
from services import atr as atr_service
from services import risk_manager
from services import ml_model
from services.portfolio import portfolio_service
from strategies import composite
from services import telegram
from config import settings

logger = logging.getLogger(__name__)
_running = True
_activity_log: deque = deque(maxlen=100)


def get_activity_log():
    return list(_activity_log)


def _log(t: str, sym: str, msg: str):
    _activity_log.appendleft({
        "time": datetime.utcnow().strftime("%H:%M"),
        "type": t,
        "symbol": sym,
        "message": msg,
    })


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

    cash = portfolio_service.get_cash_balance()
    logger.info(f"=== Cycle Started | Cash: ${cash:.2f} ===")
    _log("CYCLE", "-", f"Cycle started | Cash: ${cash:.0f}")

    for i, symbol in enumerate(settings.SYMBOLS):
        try:
            _process_symbol(symbol, db)
            if i < len(settings.SYMBOLS) - 1 and settings.DATA_SOURCE == "stocks":
                time.sleep(13)  # Alpha Vantage rate limit only
        except Exception as e:
            logger.error(f"[{symbol}] Error: {e}")

    open_count = db.query(OpenPosition).filter(OpenPosition.status == PositionStatus.OPEN).count()
    logger.info(f"=== Cycle Done | Cash: ${portfolio_service.get_cash_balance():.2f} | Open: {open_count} | Today P&L: ${get_today_pnl(db):.2f} ===")
    _log("CYCLE", "-", f"Done | Open: {open_count} | P&L today: ${get_today_pnl(db):.2f}")

def _get_prices(symbol: str):
    if settings.DATA_SOURCE == "crypto":
        return binance_svc.get_daily_prices(symbol)
    return alpha_vantage.get_daily_prices(symbol)

def _process_symbol(symbol: str, db: Session):
    df = _get_prices(symbol)
    if df.empty:
        logger.warning(f"[{symbol}] No data. Skipping.")
        return

    current_price = df.iloc[0]["close"]
    atr = atr_service.calculate(df)
    _check_open_positions(symbol, current_price, atr, db)

    result = composite.evaluate(df)
    breakdown_str = "  ".join(f"{k}:{'+' if v >= 0 else ''}{v}" for k, v in result.breakdown.items())
    ml_prob = ml_model.predict(result.breakdown)
    ml_str = f" | ML:{ml_prob:.0%}" if ml_prob is not None else ""
    logger.info(f"[{symbol}] ${current_price:.4f} | {breakdown_str} | Score:{result.score} | {result.signal}{ml_str} | ATR:{atr:.4f}")

    has_open = db.query(OpenPosition).filter(
        OpenPosition.symbol == symbol,
        OpenPosition.status == PositionStatus.OPEN
    ).first() is not None

    if result.signal == "BUY" and not has_open:
        total_open = db.query(OpenPosition).filter(OpenPosition.status == PositionStatus.OPEN).count()
        if total_open >= settings.MAX_OPEN_POSITIONS:
            logger.info(f"[{symbol}] BUY blocked — max {settings.MAX_OPEN_POSITIONS} positions already open")
            _log("BLOCKED", symbol, f"Max {settings.MAX_OPEN_POSITIONS} positions open")
        elif not _is_uptrend(df):
            logger.info(f"[{symbol}] BUY blocked — price below 50-EMA (downtrend)")
            _log("BLOCKED", symbol, "Downtrend (below EMA)")
        elif risk_manager.is_high_volatility(current_price, atr, settings.MAX_ATR_PERCENT):
            logger.info(f"[{symbol}] BUY blocked — ATR {atr:.4f} = {atr/current_price*100:.1f}% of price (too volatile)")
            _log("BLOCKED", symbol, f"High volatility ({atr/current_price*100:.1f}% ATR)")
        elif _is_low_liquidity_hour():
            logger.info(f"[{symbol}] BUY blocked — low liquidity window (01-05 UTC weekend)")
            _log("BLOCKED", symbol, "Low liquidity (01-05 UTC weekend)")
        elif ml_prob is not None and ml_prob < 0.55:
            logger.info(f"[{symbol}] BUY blocked by ML model (win probability: {ml_prob:.0%} < 55%)")
            _log("BLOCKED", symbol, f"ML: {ml_prob:.0%} win prob (< 55%)")
        else:
            _execute_buy(symbol, current_price, atr, result.score, result.breakdown, db)
    elif result.signal == "SELL" and has_open:
        _close_by_signal(symbol, current_price, db)
    else:
        logger.info(f"[{symbol}] HOLD")
        _log("HOLD", symbol, f"Score: {result.score}")

def _is_uptrend(df) -> bool:
    if settings.DISABLE_TREND_FILTER:
        return True
    if len(df) < 20:
        return True
    prices = df["close"].values[::-1][:20]
    k = 2.0 / 21
    ema = float(prices[0])
    for p in prices[1:]:
        ema = float(p) * k + ema * (1 - k)
    return float(df.iloc[0]["close"]) > ema

def _is_low_liquidity_hour() -> bool:
    """Block new buys 01:00-05:00 UTC on weekends — thin crypto order books."""
    if settings.DATA_SOURCE != "crypto":
        return False
    now = datetime.utcnow()
    return now.weekday() >= 5 and 1 <= now.hour < 5

def _check_open_positions(symbol: str, price: float, atr: float, db: Session):
    positions = db.query(OpenPosition).filter(
        OpenPosition.symbol == symbol,
        OpenPosition.status == PositionStatus.OPEN
    ).all()

    for pos in positions:
        # Breakeven: once price reaches halfway to target, move stop to entry
        halfway = pos.entry_price + (pos.target_price - pos.entry_price) * 0.5
        if price >= halfway and pos.stop_loss_price < pos.entry_price:
            logger.info(f"[{symbol}] BREAKEVEN activated — stop raised to entry ${pos.entry_price:.4f}")
            pos.stop_loss_price = pos.entry_price
            db.commit()

        # Trailing stop (only raises, never lowers)
        new_stop = risk_manager.calculate_trailing_stop(price, pos.stop_loss_price, atr)
        if new_stop > pos.stop_loss_price:
            logger.info(f"[{symbol}] Trailing stop: ${pos.stop_loss_price:.4f} → ${new_stop:.4f}")
            pos.stop_loss_price = new_stop
            db.commit()

        if price <= pos.stop_loss_price:
            pnl = (price - pos.entry_price) * pos.quantity
            logger.warning(f"[{symbol}] STOP-LOSS hit @ ${price:.4f} | P&L: {'+' if pnl >= 0 else ''}${pnl:.2f}")
            if pnl >= 0:
                telegram.notify_sell(symbol, price, pnl, "Trailing Stop (profit protected)")
            else:
                telegram.notify_stop_loss(symbol, price, abs(pnl))
            _close_position(pos, price, PositionStatus.CLOSED_STOP_LOSS, db)
        elif price >= pos.target_price:
            profit = (price - pos.entry_price) * pos.quantity
            logger.info(f"[{symbol}] TARGET hit @ ${price:.4f}")
            telegram.notify_target(symbol, price, profit)
            _close_position(pos, price, PositionStatus.CLOSED_TARGET, db)

def _execute_buy(symbol: str, price: float, atr: float, score: int, breakdown: dict, db: Session):
    cash = portfolio_service.get_cash_balance()
    qty = risk_manager.calculate_quantity(cash, price, score)

    if qty <= 0 or not portfolio_service.can_buy(qty, price):
        logger.warning(f"[{symbol}] Insufficient cash or quantity too small")
        return

    stop_loss = risk_manager.calculate_stop_loss(price, atr)
    target    = risk_manager.calculate_target(price, atr)
    mode = "PAPER TRADE" if settings.PAPER_TRADING else "LIVE TRADE"

    db.add(Trade(symbol=symbol, type=TradeType.BUY, quantity=qty, price=price,
                 total_value=qty * price, realized_pnl=0.0, notes=mode))
    db.add(OpenPosition(symbol=symbol, quantity=qty, entry_price=price,
                        stop_loss_price=stop_loss, target_price=target,
                        status=PositionStatus.OPEN,
                        entry_scores=json.dumps(breakdown)))
    db.commit()
    portfolio_service.apply_trade("BUY", symbol, qty, price)
    logger.info(f"[{symbol}] BUY {qty:.6f} @ ${price:.4f} | SL:${stop_loss:.4f} | Target:${target:.4f} | Score:{score}")
    telegram.notify_buy(symbol, price, stop_loss, target, qty)
    _log("BUY", symbol, f"{qty:.4f} @ ${price:.4f} | Score:{score}")

def _close_by_signal(symbol: str, price: float, db: Session):
    positions = db.query(OpenPosition).filter(
        OpenPosition.symbol == symbol, OpenPosition.status == PositionStatus.OPEN
    ).all()
    for pos in positions:
        if price > pos.entry_price:
            _close_position(pos, price, PositionStatus.CLOSED_SIGNAL, db)
        else:
            logger.info(f"[{symbol}] SELL signal skipped — position at loss (${price:.4f} < entry ${pos.entry_price:.4f}), stop-loss will handle it")

def _close_position(pos: OpenPosition, price: float, reason: PositionStatus, db: Session):
    pnl  = (price - pos.entry_price) * pos.quantity
    pos.exit_pnl = pnl   # recorded for ML training
    mode = "PAPER TRADE" if settings.PAPER_TRADING else "LIVE TRADE"

    db.add(Trade(symbol=pos.symbol, type=TradeType.SELL, quantity=pos.quantity,
                 price=price, total_value=pos.quantity * price, realized_pnl=pnl,
                 notes=f"{reason.value} | {mode}"))
    pos.status = reason
    db.commit()
    portfolio_service.apply_trade("SELL", pos.symbol, pos.quantity, price)
    logger.info(f"[{pos.symbol}] SELL {pos.quantity:.6f} @ ${price:.4f} | P&L:{'+' if pnl >= 0 else ''}${pnl:.2f} | {reason.value}")
    if reason == PositionStatus.CLOSED_SIGNAL:
        telegram.notify_sell(pos.symbol, price, pnl, "Signal")
    _event = "SELL" if reason == PositionStatus.CLOSED_SIGNAL else ("STOP" if reason == PositionStatus.CLOSED_STOP_LOSS else "TARGET")
    _log(_event, pos.symbol, f"@ ${price:.4f} | P&L:{'+' if pnl >= 0 else ''}${pnl:.2f}")

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
