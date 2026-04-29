import logging
import os
from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI
from database import init_db, migrate_db
from routers.trading import router
from scheduler import start_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    migrate_db()
    # Load user-saved symbols from DB so they survive redeploys
    try:
        from database import get_setting
        from config import settings
        saved = get_setting("symbols")
        if saved:
            settings.SYMBOLS = [s.strip() for s in saved.split(",") if s.strip()]
            logger.info(f"[Startup] Loaded symbols from DB: {settings.SYMBOLS}")
        else:
            logger.info(f"[Startup] No saved symbols in DB — using defaults: {settings.SYMBOLS}")
        saved_thr = get_setting("buy_threshold")
        if saved_thr:
            settings.BUY_SCORE_THRESHOLD = int(saved_thr)
            logger.info(f"[Startup] Loaded buy_threshold from DB: {settings.BUY_SCORE_THRESHOLD}")
    except Exception as e:
        logger.warning(f"[Startup] Could not load symbols from DB: {e} — using defaults")
    raw_ds = os.getenv("DATA_SOURCE", "NOT_SET")
    logger.info(f"[Startup] DATA_SOURCE raw env value: {repr(raw_ds)}")
    from config import settings as cfg
    logger.info(f"[Startup] DATA_SOURCE parsed: {repr(cfg.DATA_SOURCE)}")
    start_scheduler()
    yield

app = FastAPI(title="Trading Bot", version="1.0.0", lifespan=lifespan)
app.include_router(router)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
