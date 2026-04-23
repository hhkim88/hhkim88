from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.db.database import get_db
from app.models.celebrity import Celebrity, IndustryRanking, CelebrityProfile
from app.services.analyzer.ranker import INDUSTRIES, INDUSTRY_LABELS
from app.services.scheduler import get_last_monday

router = APIRouter(prefix="/industries", tags=["industries"])


class IndustryInfo(BaseModel):
    code: str
    label: str


class IndustryCelebrityItem(BaseModel):
    rank: int
    celebrity_id: int
    name: str
    category: Optional[str]
    profile_image_url: Optional[str]
    fit_score: float
    image_tags: list[str] = []


class IndustryRankingResponse(BaseModel):
    industry: str
    label: str
    week_start: str
    celebrities: list[IndustryCelebrityItem]


@router.get("", response_model=list[IndustryInfo])
async def list_industries():
    return [IndustryInfo(code=k, label=v) for k, v in INDUSTRY_LABELS.items()]


@router.get("/{industry}/rankings", response_model=IndustryRankingResponse)
async def get_industry_rankings(
    industry: str,
    week_start: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
):
    if industry not in INDUSTRIES:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 산업군: {industry}")

    target_week = week_start or get_last_monday()

    result = await db.execute(
        select(IndustryRanking, Celebrity, CelebrityProfile)
        .join(Celebrity, Celebrity.id == IndustryRanking.celebrity_id)
        .outerjoin(
            CelebrityProfile,
            (CelebrityProfile.celebrity_id == IndustryRanking.celebrity_id) &
            (CelebrityProfile.week_start == IndustryRanking.week_start)
        )
        .where(IndustryRanking.industry == industry)
        .where(IndustryRanking.week_start == target_week)
        .order_by(IndustryRanking.fit_score.desc())
        .limit(10)
    )
    rows = result.all()

    if not rows:
        raise HTTPException(status_code=404, detail=f"{target_week} {industry} 산업군 데이터 없음")

    celebrities = [
        IndustryCelebrityItem(
            rank=idx + 1,
            celebrity_id=celeb.id,
            name=celeb.name,
            category=celeb.category,
            profile_image_url=celeb.profile_image_url,
            fit_score=ir.fit_score or 0,
            image_tags=profile.image_tags if profile else [],
        )
        for idx, (ir, celeb, profile) in enumerate(rows)
    ]

    return IndustryRankingResponse(
        industry=industry,
        label=INDUSTRY_LABELS[industry],
        week_start=target_week.isoformat(),
        celebrities=celebrities,
    )
