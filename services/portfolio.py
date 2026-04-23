import threading
from config import settings

class PortfolioService:
    def __init__(self):
        self._cash = settings.INITIAL_BALANCE
        self._holdings: dict = {}
        self._lock = threading.Lock()

    def get_cash_balance(self) -> float:
        return self._cash

    def get_holdings(self) -> dict:
        return dict(self._holdings)

    def can_buy(self, qty: int, price: float) -> bool:
        return self._cash >= qty * price

    def apply_trade(self, trade_type: str, symbol: str, qty: int, price: float):
        with self._lock:
            if trade_type == "BUY":
                self._cash -= qty * price
                self._holdings[symbol] = self._holdings.get(symbol, 0) + qty
            else:
                self._cash += qty * price
                new_qty = self._holdings.get(symbol, 0) - qty
                if new_qty <= 0:
                    self._holdings.pop(symbol, None)
                else:
                    self._holdings[symbol] = new_qty

portfolio_service = PortfolioService()
