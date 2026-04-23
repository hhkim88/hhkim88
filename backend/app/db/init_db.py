import json
import os
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from app.db.database import engine, Base
from app.models.celebrity import Celebrity
from loguru import logger


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("DB 테이블 생성 완료")


async def seed_celebrities(db: AsyncSession):
    result = await db.execute(select(Celebrity).limit(1))
    if result.scalar_one_or_none():
        logger.info("셀럽 시드 데이터 이미 존재 - 스킵")
        return

    seed_path = Path(__file__).parent.parent.parent / "data" / "celebrities_seed.json"
    if not seed_path.exists():
        logger.warning(f"시드 파일 없음: {seed_path}")
        return

    with open(seed_path, "r", encoding="utf-8") as f:
        celebrities = json.load(f)

    for c in celebrities:
        db.add(Celebrity(**c))

    await db.commit()
    logger.info(f"셀럽 {len(celebrities)}명 시드 완료")
