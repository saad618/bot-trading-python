import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:mbCjnowMzemmplAHmgwDtZkRbLjGWzfF@metro.proxy.rlwy.net:53414/railway"
)
DB_SCHEMA = os.getenv("DB_SCHEMA", "trading")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

_is_sqlite = "sqlite" in DATABASE_URL

if _is_sqlite:
    connect_args = {"check_same_thread": False}
else:
    # psycopg2 passes options to PostgreSQL at connection time —
    # search_path is set before any query runs, including create_all
    connect_args = {"options": f"-c search_path={DB_SCHEMA}"}

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
    if not _is_sqlite:
        # Must create schema before create_all — use a connection without search_path restriction
        raw_url = DATABASE_URL  # no options here, connects to public schema by default
        setup_engine = create_engine(raw_url)
        with setup_engine.connect() as conn:
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{DB_SCHEMA}"'))
            conn.commit()
        setup_engine.dispose()
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
                conn.execute(text(sql))
                conn.commit()
            except Exception:
                pass

def get_setting(key: str, default: str = "") -> str:
    import logging
    try:
        db = SessionLocal()
        try:
            from models import AppSetting
            row = db.query(AppSetting).filter(AppSetting.key == key).first()
            return row.value if row else default
        finally:
            db.close()
    except Exception as e:
        logging.getLogger(__name__).warning(f"[DB] get_setting({key}) failed: {e}")
        return default

def set_setting(key: str, value: str):
    import logging
    try:
        db = SessionLocal()
        try:
            from models import AppSetting
            row = db.query(AppSetting).filter(AppSetting.key == key).first()
            if row:
                row.value = value
            else:
                db.add(AppSetting(key=key, value=value))
            db.commit()
            logging.getLogger(__name__).info(f"[DB] set_setting({key}) saved ({len(value)} chars)")
        finally:
            db.close()
    except Exception as e:
        logging.getLogger(__name__).error(f"[DB] set_setting({key}) failed: {e}")
