"""Claude API로 주간 셀럽 마케팅 분석 블로그 포스트 생성"""
import json
from datetime import date
from dataclasses import dataclass
from typing import Optional
import anthropic
from loguru import logger
from app.config import settings
from app.services.analyzer.ranker import INDUSTRY_LABELS


@dataclass
class BlogPost:
    title: str
    content_html: str           # 네이버 블로그용 HTML
    content_text: str           # 순수 텍스트 (로그/저장용)
    tags: list[str]
    week_start: date


BLOG_SYSTEM_PROMPT = """당신은 한국 마케팅 전문 블로거입니다.
매주 SNS 데이터와 AI 분석을 바탕으로 셀럽 마케팅 트렌드를 분석하는 인사이트 넘치는 블로그를 씁니다.
독자는 브랜드 마케터, 광고 기획자, PR 담당자입니다.
전문적이되 읽기 쉽게, 데이터 기반이되 스토리텔링이 있게 작성합니다."""

BLOG_CONTENT_PROMPT = """아래 {week_start} 주간 한국 SNS 셀럽 마케팅 분석 데이터를 바탕으로
마케팅 전문가를 위한 주간 인사이트 블로그 포스트를 작성하세요.

=== 분석 데이터 ===
{analysis_data}

=== 작성 지침 ===
1. 제목은 SEO를 고려해 작성 (예: "[2025년 N주차] 이번 주 마케팅 효과 셀럽 TOP 10 분석")
2. 본문 구성:
   - 이번 주 하이라이트 (2-3문장 요약)
   - TOP 10 랭킹 표 (HTML <table> 태그 활용)
   - 주목할 셀럽 TOP 3 상세 분석 (각 셀럽의 이미지, SNS 반응, 추천 브랜드 카테고리)
   - B2C 산업군별 추천 셀럽 TOP 5 (각 산업군별 간략 이유 포함)
   - 마케팅 담당자를 위한 핵심 인사이트 3가지
   - 다음 주 주목할 트렌드 예측
3. HTML 포맷 사용 (네이버 블로그 호환):
   - <h2>, <h3> 헤더
   - <table>, <tr>, <td> 테이블
   - <ul>, <li> 목록
   - <strong>, <em> 강조
   - <p> 단락
   - 색상은 사용하지 않음 (네이버 블로그 스타일 충돌 방지)
4. 전체 길이: 2000-3000자 분량

제목과 본문을 JSON 형식으로 반환하세요:
{{
  "title": "블로그 제목",
  "content_html": "HTML 형식 본문",
  "tags": ["셀럽마케팅", "인플루언서마케팅", "마케팅트렌드", "...최대 10개"]
}}"""


def _build_analysis_data(
    rankings: list,
    profiles: dict,
    industry_rankings: dict,
    week_start: date,
) -> str:
    """Claude 프롬프트용 분석 데이터 텍스트 구성"""
    lines = [f"[{week_start} 주간 분석]", ""]

    lines.append("▶ 주간 마케팅 효과 TOP 10:")
    for r in rankings[:10]:
        profile = profiles.get(r["name"], {})
        tags = ", ".join(profile.get("image_tags", [])[:4])
        lines.append(
            f"  {r['rank']}위 {r['name']} | 점수:{r['score']:.1f} | 언급:{r['mention_total']:,} "
            f"| 감성:{r['sentiment']:.0%} | 이미지태그:[{tags}]"
        )

    lines.append("")
    lines.append("▶ TOP 5 상세 프로파일:")
    for r in rankings[:5]:
        p = profiles.get(r["name"], {})
        if p:
            lines.append(f"  {r['name']}: {p.get('summary', '')}")
            lines.append(f"    브랜드 적합성: {p.get('brand_fit', '')}")

    lines.append("")
    lines.append("▶ 산업군별 TOP 5:")
    for industry, label in list(INDUSTRY_LABELS.items())[:10]:
        top5 = sorted(
            industry_rankings.get(industry, []),
            key=lambda x: x[1], reverse=True
        )[:5]
        names = ", ".join(f"{i+1}위 {n}({s:.0f}점)" for i, (n, s, _) in enumerate(top5))
        lines.append(f"  {label}: {names}")

    return "\n".join(lines)


async def generate_blog_post(
    rankings: list,
    profiles: dict,
    industry_rankings: dict,
    week_start: date,
) -> Optional[BlogPost]:
    """Claude API로 블로그 포스트 생성"""
    if not settings.anthropic_api_key:
        logger.warning("[BlogGenerator] API 키 없음 - 기본 블로그 반환")
        return _default_blog_post(rankings, profiles, industry_rankings, week_start)

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    analysis_data = _build_analysis_data(rankings, profiles, industry_rankings, week_start)

    try:
        message = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=BLOG_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": BLOG_CONTENT_PROMPT.format(
                    week_start=week_start.strftime("%Y년 %m월 %d일"),
                    analysis_data=analysis_data,
                ),
            }],
        )

        raw = message.content[0].text.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        data = json.loads(raw)
        content_html = data.get("content_html", "")

        return BlogPost(
            title=data.get("title", f"{week_start} 주간 셀럽 마케팅 분석"),
            content_html=content_html,
            content_text=_html_to_text(content_html),
            tags=data.get("tags", ["셀럽마케팅", "마케팅트렌드", "인플루언서"])[:10],
            week_start=week_start,
        )

    except Exception as e:
        logger.error(f"[BlogGenerator] 생성 실패: {e}")
        return _default_blog_post(rankings, profiles, industry_rankings, week_start)


def _html_to_text(html: str) -> str:
    """HTML 태그 제거하여 순수 텍스트 추출"""
    import re
    text = re.sub(r"<[^>]+>", "", html)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _default_blog_post(
    rankings: list,
    profiles: dict,
    industry_rankings: dict,
    week_start: date,
) -> BlogPost:
    """Claude API 없을 때 기본 템플릿 생성"""
    week_str = week_start.strftime("%Y년 %m월 %d일")
    top3 = rankings[:3]

    rows = "\n".join(
        f"<tr><td><strong>{r['rank']}위</strong></td><td>{r['name']}</td>"
        f"<td>{r['score']:.1f}점</td><td>{r['mention_total']:,}건</td>"
        f"<td>{r['sentiment']:.0%}</td></tr>"
        for r in rankings[:10]
    )

    industry_section = ""
    for industry, label in list(INDUSTRY_LABELS.items())[:5]:
        top5 = sorted(industry_rankings.get(industry, []), key=lambda x: x[1], reverse=True)[:5]
        names = " / ".join(f"{i+1}위 {n}" for i, (n, _, __) in enumerate(top5))
        industry_section += f"<li><strong>{label}</strong>: {names}</li>\n"

    content_html = f"""<h2>{week_str} 주간 셀럽 마케팅 효과 분석</h2>

<p>이번 주 한국 SNS(네이버 블로그, 인스타그램, 유튜브)에서 가장 활발한 마케팅 효과를 보인
셀럽은 <strong>{top3[0]['name'] if top3 else '-'}</strong>으로 나타났습니다.
매주 업데이트되는 셀럽 마케팅 인사이트를 확인해보세요.</p>

<h3>📊 주간 마케팅 효과 TOP 10</h3>
<table>
<tr><th>순위</th><th>셀럽</th><th>마케팅 점수</th><th>SNS 언급</th><th>긍정 감성</th></tr>
{rows}
</table>

<h3>🏭 B2C 산업군별 추천 셀럽 TOP 5</h3>
<ul>
{industry_section}
</ul>

<h3>💡 마케팅 담당자를 위한 인사이트</h3>
<ul>
<li>이번 주 SNS 언급량 기준 상위 셀럽을 활용한 캠페인을 검토해보세요.</li>
<li>긍정 감성 비율이 높은 셀럽은 브랜드 신뢰도 향상에 효과적입니다.</li>
<li>산업군별 적합도 점수를 참고하여 타겟 캠페인을 최적화하세요.</li>
</ul>

<p><em>본 분석은 SNS 크롤링 데이터와 Claude AI 분석을 기반으로 매주 자동 업데이트됩니다.</em></p>"""

    return BlogPost(
        title=f"[{week_str}] 셀럽 마케팅 효과 TOP 10 분석 — 이번 주 1위는?",
        content_html=content_html,
        content_text=_html_to_text(content_html),
        tags=["셀럽마케팅", "인플루언서마케팅", "마케팅트렌드", "SNS마케팅", "브랜드전략",
              "마케팅분석", "셀럽랭킹", "B2C마케팅", "주간분석", "마케팅인사이트"],
        week_start=week_start,
    )
