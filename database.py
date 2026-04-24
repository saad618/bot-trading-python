import os
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:mbCjnowMzemmplAHmgwDtZkRbLjGWzfF@metro.proxy.rlwy.net:53414/railway"
)
DB_SCHEMA = os.getenv("DB_SCHEMA", "trading")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

_is_sqlite = "sqlite" in DATABASE_URL
connect_args = {"check_same_thread": False} if _is_sqlite else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)

# Set search_path on every new Postgres connection so all queries hit the right schema
if not _is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_search_path(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute(f'SET search_path TO "{DB_SCHEMA}"')
        cursor.close()

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
        with engine.connect() as conn:
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{DB_SCHEMA}"'))
            conn.commit()
    Base.metadata.create_all(bind=engine)

def migrate_db():
    """Safely add new columns without dropping existing data."""
    schema_prefix = f'"{DB_SCHEMA}".' if not _is_sqlite else ""
    new_columns = [
        f"ALTER TABLE {schema_prefix}open_positions ADD COLUMN entry_scores TEXT",
        f"ALTER TABLE {schema_prefix}open_positions ADD COLUMN exit_pnl FLOAT",
    ]
    with engine.connect() as conn:
        for sql in new_columns:
            try:
                conn.execute(text(sql))
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
