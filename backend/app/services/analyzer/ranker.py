"""마케팅 효과 점수 계산 및 랭킹 산출"""
from dataclasses import dataclass
from datetime import date
from typing import Optional
from loguru import logger
from app.services.analyzer.mention_extractor import MentionSummary


INDUSTRIES = [
    "beauty", "food", "fashion", "electronics",
    "sports", "travel", "finance", "health",
    "entertainment", "home",
]

INDUSTRY_LABELS = {
    "beauty": "뷰티/화장품",
    "food": "식품/음료",
    "fashion": "패션/의류",
    "electronics": "전자기기/IT",
    "sports": "스포츠/레저",
    "travel": "여행/숙박",
    "finance": "금융/보험",
    "health": "건강/피트니스",
    "entertainment": "엔터테인먼트/미디어",
    "home": "홈/리빙",
}


@dataclass
class CelebrityScore:
    celebrity_id: int
    celebrity_name: str
    week_start: date
    marketing_score: float          # 0-100
    mention_total: int
    engagement_rate: float
    sentiment_avg: float
    platform_count: int
    platform_summaries: list[MentionSummary]


def _normalize(values: list[float]) -> list[float]:
    """Min-Max 정규화 (0~1)"""
    if not values:
        return values
    min_v = min(values)
    max_v = max(values)
    if max_v == min_v:
        return [0.5] * len(values)
    return [(v - min_v) / (max_v - min_v) for v in values]


def compute_engagement_rate(mention_count: int, total_likes: int, total_comments: int) -> float:
    """참여율 = (좋아요 + 댓글*2) / 언급수 (언급 없으면 0)"""
    if mention_count == 0:
        return 0.0
    return (total_likes + total_comments * 2) / mention_count


def calculate_marketing_scores(
    all_summaries: dict[int, list[MentionSummary]],
    week_start: date,
    celebrity_names: dict[int, str],
) -> list[CelebrityScore]:
    """
    all_summaries: {celebrity_id: [MentionSummary, ...]}
    celebrity_names: {celebrity_id: name}
    """
    raw_scores: list[dict] = []

    for celeb_id, summaries in all_summaries.items():
        if not summaries:
            continue

        mention_total = sum(s.mention_count for s in summaries)
        total_likes = sum(s.total_likes for s in summaries)
        total_comments = sum(s.total_comments for s in summaries)
        sentiment_avg = sum(s.sentiment_score for s in summaries) / len(summaries)
        platform_count = len(set(s.platform for s in summaries))
        engagement_rate = compute_engagement_rate(mention_total, total_likes, total_comments)

        raw_scores.append({
            "celebrity_id": celeb_id,
            "mention_total": mention_total,
            "engagement_rate": engagement_rate,
            "sentiment_avg": (sentiment_avg + 1) / 2,  # -1~1 → 0~1
            "platform_diversity": platform_count / 4,   # 최대 4개 플랫폼
            "summaries": summaries,
        })

    if not raw_scores:
        return []

    # 정규화
    mention_vals = _normalize([r["mention_total"] for r in raw_scores])
    engage_vals = _normalize([r["engagement_rate"] for r in raw_scores])

    results: list[CelebrityScore] = []
    for i, r in enumerate(raw_scores):
        score = (
            mention_vals[i]            * 0.30 +
            engage_vals[i]             * 0.35 +
            r["sentiment_avg"]         * 0.20 +
            r["platform_diversity"]    * 0.15
        ) * 100

        results.append(CelebrityScore(
            celebrity_id=r["celebrity_id"],
            celebrity_name=celebrity_names.get(r["celebrity_id"], ""),
            week_start=week_start,
            marketing_score=round(score, 2),
            mention_total=r["mention_total"],
            engagement_rate=round(r["engagement_rate"], 4),
            sentiment_avg=round(r["sentiment_avg"], 4),
            platform_count=int(r["platform_diversity"] * 4),
            platform_summaries=r["summaries"],
        ))

    results.sort(key=lambda x: x.marketing_score, reverse=True)

    logger.info(f"[Ranker] {len(results)}명 점수 계산 완료, TOP1: {results[0].celebrity_name if results else '-'}")
    return results
