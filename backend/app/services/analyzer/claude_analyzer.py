"""Claude API를 활용한 셀럽 이미지 분석 및 B2C 산업군 매칭"""
import json
from datetime import date
from dataclasses import dataclass
from typing import Optional
import anthropic
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential
from app.config import settings


INDUSTRIES = [
    "beauty", "food", "fashion", "electronics",
    "sports", "travel", "finance", "health",
    "entertainment", "home",
]

ANALYSIS_SYSTEM_PROMPT = """당신은 한국 마케팅 전문가입니다.
SNS 데이터를 분석하여 셀럽의 브랜드 이미지를 평가하고 B2C 산업군별 마케팅 적합도를 판단합니다.
반드시 유효한 JSON만 반환하세요."""

ANALYSIS_USER_PROMPT = """다음은 한국 SNS에서 수집된 {celebrity_name}에 관한 게시물과 반응입니다:

{sns_content}

위 데이터를 분석하여 정확히 아래 JSON 형식으로만 반환하세요 (설명 없이):

{{
  "image_tags": ["태그1", "태그2", "태그3", "태그4", "태그5"],
  "personality_summary": "셀럽 이미지 100자 이내 요약",
  "industry_fit": {{
    "beauty": 0,
    "food": 0,
    "fashion": 0,
    "electronics": 0,
    "sports": 0,
    "travel": 0,
    "finance": 0,
    "health": 0,
    "entertainment": 0,
    "home": 0
  }},
  "brand_fit_description": "마케팅 담당자 관점의 브랜드 적합성 설명 (200자 이내)"
}}

image_tags는 5~8개, industry_fit 점수는 0~100 정수."""


@dataclass
class CelebrityAnalysis:
    celebrity_id: int
    week_start: date
    image_tags: list[str]
    personality_summary: str
    industry_fit: dict[str, int]
    brand_fit_description: str


def _build_sns_content(celebrity_name: str, summaries: list) -> str:
    """분석용 SNS 콘텐츠 텍스트 구성"""
    lines = [f"[{celebrity_name} SNS 언급 요약]"]

    for s in summaries:
        lines.append(f"\n[{s.platform}] 언급 {s.mention_count}건, 좋아요 {s.total_likes}, 댓글 {s.total_comments}")
        lines.append(f"감성 점수: {s.sentiment_score:.2f} (-1=부정, 1=긍정)")

        sample_texts = s.raw_texts[:5]
        if sample_texts:
            lines.append("주요 텍스트 샘플:")
            for t in sample_texts:
                lines.append(f"  - {t[:150]}")

    return "\n".join(lines)[:3000]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def analyze_celebrity(
    celebrity_id: int,
    celebrity_name: str,
    week_start: date,
    summaries: list,
) -> Optional[CelebrityAnalysis]:
    """Claude API로 셀럽 이미지 분석 및 B2C 매칭"""
    if not settings.anthropic_api_key:
        logger.warning("[Claude] API 키 없음 - 기본값 반환")
        return _default_analysis(celebrity_id, celebrity_name, week_start)

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    sns_content = _build_sns_content(celebrity_name, summaries)

    try:
        message = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=ANALYSIS_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": ANALYSIS_USER_PROMPT.format(
                        celebrity_name=celebrity_name,
                        sns_content=sns_content,
                    ),
                }
            ],
        )

        raw = message.content[0].text.strip()
        # JSON 블록 추출
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        data = json.loads(raw)

        return CelebrityAnalysis(
            celebrity_id=celebrity_id,
            week_start=week_start,
            image_tags=data.get("image_tags", [])[:8],
            personality_summary=data.get("personality_summary", "")[:200],
            industry_fit={k: int(data.get("industry_fit", {}).get(k, 0)) for k in INDUSTRIES},
            brand_fit_description=data.get("brand_fit_description", "")[:500],
        )

    except json.JSONDecodeError as e:
        logger.error(f"[Claude] JSON 파싱 실패 ({celebrity_name}): {e}")
        return _default_analysis(celebrity_id, celebrity_name, week_start)
    except Exception as e:
        logger.error(f"[Claude] 분석 실패 ({celebrity_name}): {e}")
        raise


def _default_analysis(celebrity_id: int, celebrity_name: str, week_start: date) -> CelebrityAnalysis:
    """API 없을 때 기본 분석 결과"""
    return CelebrityAnalysis(
        celebrity_id=celebrity_id,
        week_start=week_start,
        image_tags=["트렌디", "인기", "SNS활발"],
        personality_summary=f"{celebrity_name}은(는) SNS에서 활발히 활동 중인 셀럽입니다.",
        industry_fit={k: 50 for k in INDUSTRIES},
        brand_fit_description="다양한 산업군에 적합한 셀럽입니다.",
    )
