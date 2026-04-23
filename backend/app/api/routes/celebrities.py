from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.db.database import get_db
from app.models.celebrity import (
    Celebrity, WeeklyRanking, CelebrityProfile, IndustryRanking
)
from app.services.analyzer.ranker import INDUSTRY_LABELS

router = APIRouter(prefix="/celebrities", tags=["celebrities"])


class IndustryFitItem(BaseModel):
    industry: str
    label: str
    fit_score: float
    rank: int


class WeeklyHistory(BaseModel):
    week_start: str
    rank: Optional[int]
    marketing_score: float


class CelebrityDetail(BaseModel):
    id: int
    name: str
    name_en: Optional[str]
    category: Optional[str]
    profile_image_url: Optional[str]
    instagram_handle: Optional[str]
    current_rank: Optional[int]
    marketing_score: float
    mention_total: int
    engagement_rate: float
    sentiment_avg: float
    image_tags: list[str]
    personality_summary: Optional[str]
    brand_fit_description: Optional[str]
    industry_fit: list[IndustryFitItem]
    weekly_history: list[WeeklyHistory]


@router.get("/{celebrity_id}", response_model=CelebrityDetail)
async def get_celebrity(celebrity_id: int, db: AsyncSession = Depends(get_db)):
    # 셀럽 기본 정보
    result = await db.execute(select(Celebrity).where(Celebrity.id == celebrity_id))
    celeb = result.scalar_one_or_none()
    if not celeb:
        raise HTTPException(status_code=404, detail="셀럽을 찾을 수 없습니다")

    # 최신 랭킹
    ranking_result = await db.execute(
        select(WeeklyRanking)
        .where(WeeklyRanking.celebrity_id == celebrity_id)
        .order_by(WeeklyRanking.week_start.desc())
        .limit(1)
    )
    latest_ranking = ranking_result.scalar_one_or_none()

    # 최신 프로파일
    profile_result = await db.execute(
        select(CelebrityProfile)
        .where(CelebrityProfile.celebrity_id == celebrity_id)
        .order_by(CelebrityProfile.week_start.desc())
        .limit(1)
    )
    profile = profile_result.scalar_one_or_none()

    # 산업군 매칭 (최신 주)
    industry_result = await db.execute(
        select(IndustryRanking)
        .where(IndustryRanking.celebrity_id == celebrity_id)
        .order_by(IndustryRanking.week_start.desc(), IndustryRanking.fit_score.desc())
        .limit(10)
    )
    industry_rows = industry_result.scalars().all()

    industry_fit = [
        IndustryFitItem(
            industry=r.industry,
            label=INDUSTRY_LABELS.get(r.industry, r.industry),
            fit_score=r.fit_score or 0,
            rank=r.rank or 0,
        )
        for r in industry_rows
    ]

    # 주간 추이 (최근 12주)
    history_result = await db.execute(
        select(WeeklyRanking)
        .where(WeeklyRanking.celebrity_id == celebrity_id)
        .order_by(WeeklyRanking.week_start.desc())
        .limit(12)
    )
    history_rows = history_result.scalars().all()

    weekly_history = [
        WeeklyHistory(
            week_start=r.week_start.isoformat(),
            rank=r.rank,
            marketing_score=r.marketing_score or 0,
        )
        for r in reversed(history_rows)
    ]

    return CelebrityDetail(
        id=celeb.id,
        name=celeb.name,
        name_en=celeb.name_en,
        category=celeb.category,
        profile_image_url=celeb.profile_image_url,
        instagram_handle=celeb.instagram_handle,
        current_rank=latest_ranking.rank if latest_ranking else None,
        marketing_score=latest_ranking.marketing_score if latest_ranking else 0,
        mention_total=latest_ranking.mention_total if latest_ranking else 0,
        engagement_rate=latest_ranking.engagement_rate if latest_ranking else 0,
        sentiment_avg=latest_ranking.sentiment_avg if latest_ranking else 0,
        image_tags=profile.image_tags if profile else [],
        personality_summary=profile.personality_summary if profile else None,
        brand_fit_description=profile.brand_fit_description if profile else None,
        industry_fit=industry_fit,
        weekly_history=weekly_history,
    )
