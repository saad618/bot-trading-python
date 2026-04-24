import enum
from datetime import datetime
from sqlalchemy import Column, Integer, Float, String, DateTime, Enum as SQLEnum
from database import Base

class TradeType(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"

class PositionStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED_TARGET = "CLOSED_TARGET"
    CLOSED_STOP_LOSS = "CLOSED_STOP_LOSS"
    CLOSED_SIGNAL = "CLOSED_SIGNAL"

class Trade(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(50), nullable=False)
    type = Column(SQLEnum(TradeType), nullable=False)
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    total_value = Column(Float, nullable=False)
    realized_pnl = Column(Float, default=0.0)
    executed_at = Column(DateTime, default=datetime.utcnow)
    notes = Column(String(200))

class OpenPosition(Base):
    __tablename__ = "open_positions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(50), nullable=False)
    quantity = Column(Float, nullable=False)
    entry_price = Column(Float, nullable=False)
    stop_loss_price = Column(Float, nullable=False)
    target_price = Column(Float, nullable=False)
    opened_at = Column(DateTime, default=datetime.utcnow)
    status = Column(SQLEnum(PositionStatus), default=PositionStatus.OPEN)
    entry_scores = Column(String, nullable=True)   # JSON: strategy breakdown at buy time
    exit_pnl = Column(Float, nullable=True)        # populated when position closes

class AppSetting(Base):
    __tablename__ = "app_settings"
    key = Column(String(100), primary_key=True)
    value = Column(String(1000), nullable=False)
