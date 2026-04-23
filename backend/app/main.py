from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.db.database import AsyncSessionLocal
from app.db.init_db import create_tables, seed_celebrities
from app.services.scheduler import setup_scheduler, scheduler
from app.api.routes import rankings, celebrities, industries


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작
    logger.info("서버 시작 중...")
    await create_tables()
    async with AsyncSessionLocal() as db:
        await seed_celebrities(db)
    setup_scheduler()
    yield
    # 종료
    scheduler.shutdown()
    logger.info("서버 종료")


app = FastAPI(
    title="Korean Celebrity Marketing Analysis API",
    description="한국 SNS 셀럽 마케팅 효과 분석 서비스",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://frontend:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rankings.router, prefix="/api/v1")
app.include_router(celebrities.router, prefix="/api/v1")
app.include_router(industries.router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}
