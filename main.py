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

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    migrate_db()
    start_scheduler()
    yield

app = FastAPI(title="Trading Bot", version="1.0.0", lifespan=lifespan)
app.include_router(router)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
