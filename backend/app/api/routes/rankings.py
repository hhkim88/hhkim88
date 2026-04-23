from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
import json
import redis.asyncio as aioredis

from app.db.database import get_db
from app.models.celebrity import Celebrity, WeeklyRanking, CelebrityProfile
from app.config import settings
from app.services.scheduler import run_weekly_update, get_last_monday
from loguru import logger

router = APIRouter(prefix="/rankings", tags=["rankings"])

_redis: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


class RankingItem(BaseModel):
    rank: int
    celebrity_id: int
    name: str
    category: Optional[str]
    profile_image_url: Optional[str]
    marketing_score: float
    mention_total: int
    engagement_rate: float
    sentiment_avg: float
    image_tags: list[str] = []
    personality_summary: Optional[str] = None


class RankingResponse(BaseModel):
    week_start: str
    updated_at: Optional[str] = None
    rankings: list[RankingItem]


async def _fetch_rankings(db: AsyncSession, week_start: date) -> list[RankingItem]:
    result = await db.execute(
        select(WeeklyRanking, Celebrity, CelebrityProfile)
        .join(Celebrity, Celebrity.id == WeeklyRanking.celebrity_id)
        .outerjoin(
            CelebrityProfile,
            (CelebrityProfile.celebrity_id == WeeklyRanking.celebrity_id) &
            (CelebrityProfile.week_start == WeeklyRanking.week_start)
        )
        .where(WeeklyRanking.week_start == week_start)
        .order_by(WeeklyRanking.rank)
    )
    rows = result.all()

    items = []
    for ranking, celeb, profile in rows:
        items.append(RankingItem(
            rank=ranking.rank,
            celebrity_id=celeb.id,
            name=celeb.name,
            category=celeb.category,
            profile_image_url=celeb.profile_image_url,
            marketing_score=ranking.marketing_score or 0,
            mention_total=ranking.mention_total or 0,
            engagement_rate=ranking.engagement_rate or 0,
            sentiment_avg=ranking.sentiment_avg or 0,
            image_tags=profile.image_tags if profile else [],
            personality_summary=profile.personality_summary if profile else None,
        ))

    return items


@router.get("/current", response_model=RankingResponse)
async def get_current_rankings(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    cache_key = "rankings:current"
    cached = await redis.get(cache_key)
    if cached:
        return RankingResponse(**json.loads(cached))

    week_start = get_last_monday()
    items = await _fetch_rankings(db, week_start)

    if not items:
        raise HTTPException(status_code=404, detail="아직 랭킹 데이터가 없습니다. 관리자 업데이트를 실행해주세요.")

    resp = RankingResponse(week_start=week_start.isoformat(), rankings=items)
    await redis.setex(cache_key, settings.cache_ttl_rankings, resp.model_dump_json())
    return resp


@router.get("/{week_start}", response_model=RankingResponse)
async def get_rankings_by_week(
    week_start: date,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    cache_key = f"rankings:{week_start.isoformat()}"
    cached = await redis.get(cache_key)
    if cached:
        return RankingResponse(**json.loads(cached))

    items = await _fetch_rankings(db, week_start)
    if not items:
        raise HTTPException(status_code=404, detail=f"{week_start} 주간 랭킹 데이터 없음")

    resp = RankingResponse(week_start=week_start.isoformat(), rankings=items)
    await redis.setex(cache_key, settings.cache_ttl_rankings, resp.model_dump_json())
    return resp


@router.post("/admin/trigger-update")
async def trigger_weekly_update(
    background_tasks: BackgroundTasks,
    week_start: Optional[date] = None,
):
    """수동으로 주간 업데이트 실행 (테스트/관리용)"""
    target_week = week_start or get_last_monday()
    logger.info(f"[API] 수동 업데이트 트리거: {target_week}")
    background_tasks.add_task(run_weekly_update, target_week)
    return {"message": f"{target_week} 주간 업데이트 시작됨 (백그라운드)"}
