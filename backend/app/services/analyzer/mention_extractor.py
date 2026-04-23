"""SNS 수집 데이터에서 셀럽 언급 집계 및 감성 점수 산출"""
import re
from datetime import date
from dataclasses import dataclass, field
from typing import Optional
from loguru import logger


# 긍정/부정 키워드 사전 (Korean)
POSITIVE_KEYWORDS = [
    "좋아", "사랑", "최고", "멋지", "예쁘", "훈훈", "귀엽", "대박",
    "짱", "완벽", "팬", "응원", "행복", "기대", "설레", "감동",
    "칭찬", "인정", "섹시", "매력", "비주얼", "갓", "레전드",
]
NEGATIVE_KEYWORDS = [
    "싫어", "별로", "실망", "최악", "욕", "비난", "논란", "스캔들",
    "거짓", "허위", "싫다", "짜증", "화남", "불쾌", "역겨", "나쁘",
]


@dataclass
class MentionSummary:
    celebrity_id: int
    celebrity_name: str
    week_start: date
    platform: str
    mention_count: int = 0
    total_likes: int = 0
    total_comments: int = 0
    sentiment_score: float = 0.0      # -1.0 ~ 1.0
    raw_texts: list[str] = field(default_factory=list)


def calculate_sentiment(texts: list[str]) -> float:
    """간단한 키워드 기반 감성 점수 계산 (-1.0 ~ 1.0)"""
    if not texts:
        return 0.0

    pos_count = 0
    neg_count = 0
    total = len(texts)

    for text in texts:
        text_lower = text.lower()
        pos = sum(1 for kw in POSITIVE_KEYWORDS if kw in text_lower)
        neg = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text_lower)

        if pos > neg:
            pos_count += 1
        elif neg > pos:
            neg_count += 1

    if total == 0:
        return 0.0

    return (pos_count - neg_count) / total


def extract_engagement_text(title: str, content: str) -> str:
    """게시글에서 감성 분석용 텍스트 추출"""
    combined = f"{title} {content}"
    combined = re.sub(r"https?://\S+", "", combined)
    combined = re.sub(r"[^\w\s가-힣]", " ", combined)
    return combined[:500]


def aggregate_naver_mentions(
    celebrity_id: int,
    celebrity_name: str,
    week_start: date,
    posts: list,
) -> list[MentionSummary]:
    """네이버 블로그/카페 게시물 집계"""
    platform_map: dict[str, MentionSummary] = {}

    for post in posts:
        platform = post.platform
        if platform not in platform_map:
            platform_map[platform] = MentionSummary(
                celebrity_id=celebrity_id,
                celebrity_name=celebrity_name,
                week_start=week_start,
                platform=platform,
            )

        s = platform_map[platform]
        s.mention_count += 1
        s.total_likes += post.likes
        s.total_comments += post.comments
        text = extract_engagement_text(post.title, post.content_preview)
        s.raw_texts.append(text)

    for s in platform_map.values():
        s.sentiment_score = calculate_sentiment(s.raw_texts)

    return list(platform_map.values())


def aggregate_instagram_mentions(
    celebrity_id: int,
    celebrity_name: str,
    week_start: date,
    posts: list,
) -> MentionSummary:
    """인스타그램 게시물 집계"""
    summary = MentionSummary(
        celebrity_id=celebrity_id,
        celebrity_name=celebrity_name,
        week_start=week_start,
        platform="instagram",
    )

    for post in posts:
        summary.mention_count += 1
        summary.total_likes += post.likes
        summary.total_comments += post.comments
        summary.raw_texts.append(post.caption[:300])

    summary.sentiment_score = calculate_sentiment(summary.raw_texts)
    return summary


def aggregate_youtube_mentions(
    celebrity_id: int,
    celebrity_name: str,
    week_start: date,
    videos: list,
) -> MentionSummary:
    """유튜브 데이터 집계"""
    summary = MentionSummary(
        celebrity_id=celebrity_id,
        celebrity_name=celebrity_name,
        week_start=week_start,
        platform="youtube",
    )

    for video in videos:
        summary.mention_count += 1
        summary.total_likes += video.like_count
        summary.total_comments += video.comment_count
        for comment in video.top_comments:
            summary.raw_texts.append(comment[:200])

    summary.sentiment_score = calculate_sentiment(summary.raw_texts)
    return summary
