from config import settings

def calculate_quantity(cash: float, price: float) -> int:
    if price <= 0:
        return 0
    return max(1, int(cash * (settings.POSITION_SIZE_PERCENT / 100.0) / price))

def calculate_stop_loss(entry: float, atr: float) -> float:
    if atr > 0:
        return round(entry - atr * 2, 2)
    return round(entry * (1 - settings.STOP_LOSS_PERCENT / 100.0), 2)

def calculate_target(entry: float, atr: float) -> float:
    if atr > 0:
        return round(entry + atr * 3, 2)
    return round(entry * (1 + settings.TARGET_PERCENT / 100.0), 2)

def is_high_volatility(price: float, atr: float, max_atr_pct: float = 4.0) -> bool:
    """True when ATR exceeds max_atr_pct% of price — flags gap/whipsaw risk."""
    if price <= 0 or atr <= 0:
        return False
    return (atr / price * 100) > max_atr_pct

def calculate_trailing_stop(current_price: float, current_stop: float, atr: float) -> float:
    if atr > 0:
        new_stop = round(current_price - atr * 2, 2)
    else:
        new_stop = round(current_price * (1 - settings.STOP_LOSS_PERCENT / 100.0), 2)
    return new_stop if new_stop > current_stop else current_stop
