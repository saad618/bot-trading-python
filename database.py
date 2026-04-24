import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./trading.db")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    from models import Trade, OpenPosition, AppSetting
    Base.metadata.create_all(bind=engine)

def migrate_db():
    """Safely add new columns without dropping existing data."""
    new_columns = [
        "ALTER TABLE open_positions ADD COLUMN entry_scores TEXT",
        "ALTER TABLE open_positions ADD COLUMN exit_pnl FLOAT",
    ]
    with engine.connect() as conn:
        for sql in new_columns:
            try:
                conn.execute(__import__("sqlalchemy").text(sql))
                conn.commit()
            except Exception:
                pass

def get_setting(key: str, default: str = "") -> str:
    db = SessionLocal()
    try:
        from models import AppSetting
        row = db.query(AppSetting).filter(AppSetting.key == key).first()
        return row.value if row else default
    finally:
        db.close()

def set_setting(key: str, value: str):
    db = SessionLocal()
    try:
        from models import AppSetting
        import sqlalchemy
        row = db.query(AppSetting).filter(AppSetting.key == key).first()
        if row:
            row.value = value
        else:
            db.add(AppSetting(key=key, value=value))
        db.commit()
    finally:
        db.close()
