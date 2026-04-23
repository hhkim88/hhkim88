"""
한국 SNS 셀럽 마케팅 분석 서비스 — 샘플 데모

실제 SNS 수집 대신 현실적인 모의 데이터로 전체 파이프라인을 시연합니다.
Claude API 키가 있으면 실제 AI 분석을 수행하고, 없으면 시뮬레이션 결과를 사용합니다.
"""

import json
import os
import asyncio
import random
from datetime import date, timedelta
from dataclasses import dataclass, field
from typing import Optional

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.columns import Columns
    from rich import box
    from rich.text import Text
    from rich.progress import Progress, SpinnerColumn, TextColumn
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

# ── 모의 SNS 데이터 ───────────────────────────────────────────────────────────

MOCK_SNS_DATA = {
    "아이유": {
        "naver_blog":   {"mentions": 8420, "likes": 312000, "comments": 28400, "sentiment": 0.87},
        "naver_cafe":   {"mentions": 3200, "likes": 98000,  "comments": 11200, "sentiment": 0.84},
        "instagram":    {"mentions": 15600, "likes": 890000, "comments": 42000, "sentiment": 0.91},
        "youtube":      {"mentions": 2100, "likes": 145000, "comments": 18900, "sentiment": 0.88},
        "sample_texts": [
            "아이유 신곡 진짜 미쳤다 이미 50번 들음ㅠ",
            "아이유 광고 나왔는데 너무 예쁘다 저 제품 사야겠다",
            "아이유 팬미팅 다녀왔는데 꿈만 같아요 너무 행복",
            "아이유 드라마 시청률 대박이네 역시 국민 배우",
        ],
    },
    "BTS 뷔": {
        "naver_blog":   {"mentions": 11200, "likes": 420000, "comments": 35600, "sentiment": 0.92},
        "naver_cafe":   {"mentions": 4800,  "likes": 180000, "comments": 22000, "sentiment": 0.90},
        "instagram":    {"mentions": 28400, "likes": 2100000, "comments": 95000, "sentiment": 0.93},
        "youtube":      {"mentions": 3400,  "likes": 210000, "comments": 31000, "sentiment": 0.89},
        "sample_texts": [
            "뷔 솔로 앨범 발매 소식에 전세계 아미들 난리남",
            "태형 인스타 업데이트 보고 심장 멎을 뻔 했다",
            "뷔 명품 브랜드 앰배서더 된 거 너무 잘 어울림",
            "방탄 뷔 런웨이 모습 보고 패션 완전 따라함",
        ],
    },
    "블랙핑크 제니": {
        "naver_blog":   {"mentions": 9800,  "likes": 380000, "comments": 29000, "sentiment": 0.85},
        "naver_cafe":   {"mentions": 3900,  "likes": 142000, "comments": 17800, "sentiment": 0.83},
        "instagram":    {"mentions": 24600, "likes": 1850000, "comments": 78000, "sentiment": 0.86},
        "youtube":      {"mentions": 2800,  "likes": 175000, "comments": 24000, "sentiment": 0.84},
        "sample_texts": [
            "제니 솔로 컴백 티저 공개됨 비주얼 미쳤다",
            "제니 샤넬 행사 직캠 보다가 패션 감각에 감탄",
            "제니 광고 나온 화장품 완판됐다고 함",
            "블핑 제니 스타일 항상 트렌드 선도하는 느낌",
        ],
    },
    "임영웅": {
        "naver_blog":   {"mentions": 12800, "likes": 285000, "comments": 41000, "sentiment": 0.94},
        "naver_cafe":   {"mentions": 8900,  "likes": 198000, "comments": 35000, "sentiment": 0.95},
        "instagram":    {"mentions": 6400,  "likes": 320000, "comments": 28000, "sentiment": 0.93},
        "youtube":      {"mentions": 5200,  "likes": 248000, "comments": 42000, "sentiment": 0.96},
        "sample_texts": [
            "임영웅 콘서트 티켓 5분 만에 매진 진짜 대단하다",
            "임영웅 신보 빌보드 차트 진입했다니 역시",
            "영웅이 광고 보고 그 식품 무조건 사봐야겠다",
            "임영웅 팬층이 정말 두텁다 30대 이상도 엄청 많아",
        ],
    },
    "손흥민": {
        "naver_blog":   {"mentions": 14200, "likes": 510000, "comments": 58000, "sentiment": 0.89},
        "naver_cafe":   {"mentions": 6100,  "likes": 220000, "comments": 29000, "sentiment": 0.88},
        "instagram":    {"mentions": 18900, "likes": 1200000, "comments": 62000, "sentiment": 0.91},
        "youtube":      {"mentions": 7800,  "likes": 380000, "comments": 48000, "sentiment": 0.90},
        "sample_texts": [
            "손흥민 해트트릭 달성 진짜 자랑스럽다 국가대표",
            "흥민이 광고 모델 된 음료 마셔봤는데 맛있음",
            "손흥민 스포츠 브랜드 콜라보 운동화 품절됨",
            "토트넘 손흥민 활약 보고 영국 팬들도 반했다고",
        ],
    },
    "아이린": {
        "naver_blog":   {"mentions": 5400,  "likes": 190000, "comments": 18200, "sentiment": 0.72},
        "naver_cafe":   {"mentions": 2100,  "likes": 78000,  "comments": 9800,  "sentiment": 0.70},
        "instagram":    {"mentions": 9800,  "likes": 620000, "comments": 31000, "sentiment": 0.74},
        "youtube":      {"mentions": 1200,  "likes": 68000,  "comments": 8900,  "sentiment": 0.71},
        "sample_texts": [
            "레드벨벳 아이린 신곡 뮤비 비주얼 완성체",
            "아이린 화보 보다가 시간 다 보냄 진짜 예쁘다",
        ],
    },
    "에스파 카리나": {
        "naver_blog":   {"mentions": 7200,  "likes": 265000, "comments": 22000, "sentiment": 0.83},
        "naver_cafe":   {"mentions": 2800,  "likes": 98000,  "comments": 13000, "sentiment": 0.81},
        "instagram":    {"mentions": 13400, "likes": 780000, "comments": 38000, "sentiment": 0.85},
        "youtube":      {"mentions": 1900,  "likes": 112000, "comments": 15000, "sentiment": 0.82},
        "sample_texts": [
            "카리나 비주얼 진짜 AI 같음 사람이 맞냐",
            "에스파 카리나 럭셔리 브랜드 앰배서더 완벽한 선택",
            "카리나 패션 따라하려고 옷 새로 삼",
        ],
    },
    "뉴진스 해린": {
        "naver_blog":   {"mentions": 6800,  "likes": 245000, "comments": 19800, "sentiment": 0.90},
        "naver_cafe":   {"mentions": 2400,  "likes": 88000,  "comments": 11500, "sentiment": 0.89},
        "instagram":    {"mentions": 16200, "likes": 920000, "comments": 45000, "sentiment": 0.91},
        "youtube":      {"mentions": 2200,  "likes": 128000, "comments": 18000, "sentiment": 0.88},
        "sample_texts": [
            "해린 직캠 보고 완전 팬됨 귀여움 폭발",
            "뉴진스 해린 뷰티 브랜드 광고 청순미 넘쳐",
            "해린 스타일 10대들 사이에서 엄청 유행",
        ],
    },
    "박보검": {
        "naver_blog":   {"mentions": 4800,  "likes": 175000, "comments": 16400, "sentiment": 0.86},
        "naver_cafe":   {"mentions": 1900,  "likes": 68000,  "comments": 8900,  "sentiment": 0.85},
        "instagram":    {"mentions": 8400,  "likes": 520000, "comments": 26000, "sentiment": 0.87},
        "youtube":      {"mentions": 1100,  "likes": 72000,  "comments": 9800,  "sentiment": 0.84},
        "sample_texts": [
            "박보검 드라마 복귀 소식에 팬들 설레는 중",
            "보검이 광고 나온 남성 화장품 남자친구한테 선물함",
            "박보검 신사적인 이미지 여전히 건재",
        ],
    },
    "이효리": {
        "naver_blog":   {"mentions": 5100,  "likes": 168000, "comments": 21000, "sentiment": 0.80},
        "naver_cafe":   {"mentions": 1800,  "likes": 62000,  "comments": 9200,  "sentiment": 0.78},
        "instagram":    {"mentions": 7200,  "likes": 410000, "comments": 22000, "sentiment": 0.81},
        "youtube":      {"mentions": 2400,  "likes": 142000, "comments": 16000, "sentiment": 0.79},
        "sample_texts": [
            "이효리 자연주의 라이프스타일 영향 받아서 채식 시작",
            "효리 유기농 브랜드 콜라보 제품 사봤는데 좋음",
            "이효리 제주도 생활 보면서 힐링된다",
        ],
    },
    "전지현": {
        "naver_blog":   {"mentions": 4200,  "likes": 145000, "comments": 14800, "sentiment": 0.88},
        "naver_cafe":   {"mentions": 1600,  "likes": 58000,  "comments": 7800,  "sentiment": 0.87},
        "instagram":    {"mentions": 5800,  "likes": 380000, "comments": 18000, "sentiment": 0.89},
        "youtube":      {"mentions": 900,   "likes": 52000,  "comments": 7200,  "sentiment": 0.86},
        "sample_texts": [
            "전지현 드라마 복귀작 기다리는 사람 손",
            "지현 씨 명품 광고 품격 다르다 역시 국민 배우",
            "전지현 스타일 40대인데 20대보다 예쁨",
        ],
    },
    "지드래곤": {
        "naver_blog":   {"mentions": 9400,  "likes": 340000, "comments": 31000, "sentiment": 0.82},
        "naver_cafe":   {"mentions": 3200,  "likes": 118000, "comments": 16000, "sentiment": 0.80},
        "instagram":    {"mentions": 19800, "likes": 1450000, "comments": 68000, "sentiment": 0.84},
        "youtube":      {"mentions": 4100,  "likes": 230000, "comments": 28000, "sentiment": 0.81},
        "sample_texts": [
            "GD 컴백 소식에 SNS 난리났다 기다렸다",
            "지드래곤 스트리트 패션 트렌드 여전히 선도",
            "GD 향수 브랜드 콜라보 엄청난 화제",
            "권지용 아트 프로젝트 너무 독창적이다",
        ],
    },
    "수지": {
        "naver_blog":   {"mentions": 5600,  "likes": 198000, "comments": 19200, "sentiment": 0.87},
        "naver_cafe":   {"mentions": 2200,  "likes": 78000,  "comments": 10800, "sentiment": 0.85},
        "instagram":    {"mentions": 10400, "likes": 680000, "comments": 32000, "sentiment": 0.88},
        "youtube":      {"mentions": 1400,  "likes": 88000,  "comments": 12000, "sentiment": 0.86},
        "sample_texts": [
            "수지 광고 나온 음료 마트에서 찾아봄",
            "배수지 드라마 시청률 쭉쭉 오르는 중",
            "수지 내추럴 메이크업 따라해봤는데 완전 예쁨",
        ],
    },
    "김수현": {
        "naver_blog":   {"mentions": 4500,  "likes": 162000, "comments": 15800, "sentiment": 0.83},
        "naver_cafe":   {"mentions": 1700,  "likes": 62000,  "comments": 8400,  "sentiment": 0.82},
        "instagram":    {"mentions": 8200,  "likes": 540000, "comments": 25000, "sentiment": 0.84},
        "youtube":      {"mentions": 1100,  "likes": 72000,  "comments": 9800,  "sentiment": 0.82},
        "sample_texts": [
            "김수현 드라마 연기력 역대급이다",
            "수현 씨 모델 브랜드 남자친구한테 사줌",
        ],
    },
    "이영지": {
        "naver_blog":   {"mentions": 3800,  "likes": 128000, "comments": 18000, "sentiment": 0.86},
        "naver_cafe":   {"mentions": 1400,  "likes": 48000,  "comments": 8200,  "sentiment": 0.84},
        "instagram":    {"mentions": 7800,  "likes": 420000, "comments": 28000, "sentiment": 0.87},
        "youtube":      {"mentions": 3200,  "likes": 185000, "comments": 22000, "sentiment": 0.85},
        "sample_texts": [
            "이영지 유튜브 채널 구독자 폭발적으로 늘고 있음",
            "영지 광고 보고 그 스낵 사먹었는데 맛있음",
            "이영지 자연스러운 매력 MZ세대 완전 열광",
        ],
    },
}

# ── 마케팅 점수 계산 ─────────────────────────────────────────────────────────

def normalize_list(values):
    min_v, max_v = min(values), max(values)
    if max_v == min_v:
        return [0.5] * len(values)
    return [(v - min_v) / (max_v - min_v) for v in values]


def compute_scores(data):
    names = list(data.keys())
    raw = []
    for name in names:
        d = data[name]
        total_mentions = sum(p["mentions"] for p in d.values() if isinstance(p, dict) and "mentions" in p)
        total_likes    = sum(p["likes"]    for p in d.values() if isinstance(p, dict) and "likes"    in p)
        total_comments = sum(p["comments"] for p in d.values() if isinstance(p, dict) and "comments" in p)
        sentiments     = [p["sentiment"] for p in d.values() if isinstance(p, dict) and "sentiment" in p]
        sentiment_avg  = sum(sentiments) / len(sentiments) if sentiments else 0.5
        platform_count = sum(1 for k in d if k != "sample_texts" and isinstance(d[k], dict))
        engagement     = (total_likes + total_comments * 2) / max(total_mentions, 1)

        raw.append({
            "name": name,
            "mention_total": total_mentions,
            "engagement": engagement,
            "sentiment": sentiment_avg,
            "platform_div": platform_count / 4,
        })

    mention_norm = normalize_list([r["mention_total"] for r in raw])
    engage_norm  = normalize_list([r["engagement"] for r in raw])

    results = []
    for i, r in enumerate(raw):
        score = (
            mention_norm[i]    * 0.30 +
            engage_norm[i]     * 0.35 +
            r["sentiment"]     * 0.20 +
            r["platform_div"]  * 0.15
        ) * 100
        results.append({**r, "score": round(score, 1)})

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


# ── Claude API 분석 ───────────────────────────────────────────────────────────

MOCK_PROFILES = {
    "아이유": {
        "image_tags": ["국민 여동생", "신뢰감", "다재다능", "청순미", "감성적", "20-40대 공감"],
        "summary": "음악·연기·예능 넘나드는 전천후 아티스트. 세대를 초월한 높은 호감도와 신뢰감 보유.",
        "industry_fit": {"beauty": 92, "food": 85, "fashion": 88, "electronics": 72, "sports": 45,
                         "travel": 82, "finance": 78, "health": 76, "entertainment": 95, "home": 80},
        "brand_fit": "뷰티·패션·식품 분야에서 높은 신뢰도를 기반으로 구매 전환율 최상위권. 특히 20-30대 여성 타겟 제품에 최적.",
    },
    "BTS 뷔": {
        "image_tags": ["글로벌 아이콘", "럭셔리", "아티스틱", "트렌드세터", "감성비주얼", "MZ 열광"],
        "summary": "전 세계 팬덤을 보유한 K-팝 아이콘. 럭셔리 브랜드와 예술적 감각이 완벽히 매칭.",
        "industry_fit": {"beauty": 88, "food": 65, "fashion": 98, "electronics": 85, "sports": 62,
                         "travel": 78, "finance": 55, "health": 70, "entertainment": 96, "home": 60},
        "brand_fit": "패션·뷰티·전자기기 영역에서 글로벌 인지도를 활용한 프리미엄 포지셔닝에 최적. 럭셔리 브랜드 앰배서더 효과 극대화.",
    },
    "블랙핑크 제니": {
        "image_tags": ["럭셔리 아이콘", "패션 피플", "쿨한 이미지", "글로벌", "트렌디", "프리미엄"],
        "summary": "샤넬 앰배서더로 대표되는 글로벌 패션 아이콘. 럭셔리·프리미엄 브랜드와 시너지 극대화.",
        "industry_fit": {"beauty": 95, "food": 58, "fashion": 99, "electronics": 80, "sports": 50,
                         "travel": 82, "finance": 60, "health": 72, "entertainment": 94, "home": 65},
        "brand_fit": "뷰티·패션 카테고리 넘버원 셀럽. 럭셔리 포지셔닝 필요한 브랜드의 1순위 선택지.",
    },
    "임영웅": {
        "image_tags": ["국민 남동생", "진정성", "30-50대 팬덤", "트로트 아이콘", "신뢰", "감동"],
        "summary": "트로트 신드롬을 일으킨 국민 가수. 중장년층 팬덤이 두텁고 소비력 높은 연령대와 매칭.",
        "industry_fit": {"beauty": 65, "food": 92, "fashion": 70, "electronics": 75, "sports": 55,
                         "travel": 80, "finance": 88, "health": 85, "entertainment": 96, "home": 82},
        "brand_fit": "식품·금융·건강 카테고리에서 30-50대 소비자 타겟 마케팅 효과 최상위. 신뢰도 기반 구매 전환율 탁월.",
    },
    "손흥민": {
        "image_tags": ["스포츠 영웅", "국가 자긍심", "글로벌", "도전정신", "성실", "남성 롤모델"],
        "summary": "EPL 최고 득점자 출신의 글로벌 스포츠 스타. 남성 소비자 영향력 1위, 국민적 자긍심 상징.",
        "industry_fit": {"beauty": 55, "food": 82, "fashion": 78, "electronics": 90, "sports": 99,
                         "travel": 72, "finance": 85, "health": 95, "entertainment": 88, "home": 60},
        "brand_fit": "스포츠·건강·전자기기·금융 분야에서 남성 20-40대 타겟 마케팅 최적화. 글로벌 인지도로 해외 시장 동시 공략 가능.",
    },
}

DEFAULT_PROFILE = {
    "image_tags": ["트렌디", "인기", "SNS 활발", "팬덤 보유"],
    "summary": "SNS에서 활발히 활동 중인 인기 셀럽.",
    "industry_fit": {k: random.randint(55, 85) for k in
                     ["beauty","food","fashion","electronics","sports","travel","finance","health","entertainment","home"]},
    "brand_fit": "다양한 B2C 산업군에 적용 가능한 셀럽입니다.",
}

INDUSTRY_LABELS = {
    "beauty": "💄 뷰티/화장품", "food": "🍱 식품/음료",
    "fashion": "👗 패션/의류",   "electronics": "💻 전자기기",
    "sports": "⚽ 스포츠",       "travel": "✈️ 여행",
    "finance": "💰 금융",         "health": "💪 건강/피트니스",
    "entertainment": "🎬 엔터테인먼트", "home": "🏠 홈/리빙",
}


async def run_demo():
    if HAS_RICH:
        console = Console()
    else:
        console = None

    def print_h(text, style="bold blue"):
        if console:
            console.print(f"\n{text}", style=style)
        else:
            print(f"\n{'='*60}\n{text}\n{'='*60}")

    def print_line(text=""):
        if console:
            console.print(text)
        else:
            print(text)

    # ─── 헤더 ────────────────────────────────────────────────────────────────
    week_start = date.today() - timedelta(days=date.today().weekday())

    if console:
        console.print(Panel.fit(
            f"[bold cyan]한국 SNS 셀럽 마케팅 분석 서비스[/]\n"
            f"[dim]{week_start.strftime('%Y년 %m월 %d일')} 주간 기준 · 15명 분석[/dim]",
            border_style="cyan",
        ))
    else:
        print("\n" + "="*70)
        print(" 한국 SNS 셀럽 마케팅 분석 서비스")
        print(f" {week_start.strftime('%Y년 %m월 %d일')} 주간 기준 · 15명 분석")
        print("="*70)

    # ─── 1단계: SNS 데이터 수집 시뮬레이션 ──────────────────────────────────
    print_h("① SNS 데이터 수집 현황", style="bold yellow")

    if console:
        tbl = Table(box=box.ROUNDED, show_header=True, header_style="bold white on dark_blue")
        tbl.add_column("셀럽", style="bold", width=14)
        tbl.add_column("네이버 블로그", justify="right")
        tbl.add_column("인스타그램", justify="right")
        tbl.add_column("유튜브", justify="right")
        tbl.add_column("총 언급", justify="right", style="bold cyan")
        for name, d in list(MOCK_SNS_DATA.items())[:8]:
            nb  = d.get("naver_blog",  {}).get("mentions", 0)
            ig  = d.get("instagram",   {}).get("mentions", 0)
            yt  = d.get("youtube",     {}).get("mentions", 0)
            tot = nb + d.get("naver_cafe", {}).get("mentions", 0) + ig + yt
            tbl.add_row(name, f"{nb:,}", f"{ig:,}", f"{yt:,}", f"{tot:,}")
        console.print(tbl)
    else:
        print(f"{'셀럽':<14} {'네이버':>10} {'인스타':>10} {'유튜브':>8} {'총언급':>10}")
        print("-"*56)
        for name, d in list(MOCK_SNS_DATA.items())[:8]:
            nb  = d.get("naver_blog",  {}).get("mentions", 0)
            ig  = d.get("instagram",   {}).get("mentions", 0)
            yt  = d.get("youtube",     {}).get("mentions", 0)
            tot = nb + d.get("naver_cafe", {}).get("mentions", 0) + ig + yt
            print(f"{name:<14} {nb:>10,} {ig:>10,} {yt:>8,} {tot:>10,}")

    # ─── 2단계: 마케팅 점수 계산 ─────────────────────────────────────────────
    print_h("② 마케팅 효과 점수 계산", style="bold yellow")
    print_line("[dim]점수 = 언급량(30%) + 참여율(35%) + 긍정감성(20%) + 플랫폼다양성(15%)[/dim]"
               if console else "점수 = 언급량(30%) + 참여율(35%) + 긍정감성(20%) + 플랫폼다양성(15%)")

    scores = compute_scores(MOCK_SNS_DATA)

    # ─── 3단계: TOP 10 랭킹 ──────────────────────────────────────────────────
    print_h("③ 주간 마케팅 효과 셀럽 TOP 10", style="bold green")

    rank_icons = {1: "🥇", 2: "🥈", 3: "🥉"}

    if console:
        tbl = Table(box=box.ROUNDED, show_header=True, header_style="bold white on dark_green")
        tbl.add_column("순위", width=4, justify="center")
        tbl.add_column("셀럽명", style="bold", width=16)
        tbl.add_column("마케팅 점수", justify="center", width=12)
        tbl.add_column("총 언급", justify="right", width=10)
        tbl.add_column("참여율", justify="right", width=8)
        tbl.add_column("감성", justify="right", width=6)
        tbl.add_column("이미지 태그", width=30)

        for rank, s in enumerate(scores[:10], 1):
            icon  = rank_icons.get(rank, str(rank))
            profile = MOCK_PROFILES.get(s["name"], DEFAULT_PROFILE)
            tags  = "  ".join(f"[blue]{t}[/]" for t in profile["image_tags"][:3])
            score_style = "bold green" if s["score"] >= 70 else "bold yellow" if s["score"] >= 50 else "white"
            tbl.add_row(
                f"{icon}",
                s["name"],
                f"[{score_style}]{s['score']:.1f}[/]",
                f"{s['mention_total']:,}",
                f"{s['engagement']:.1f}",
                f"{s['sentiment']:.0%}",
                tags,
            )
        console.print(tbl)
    else:
        print(f"\n{'순위':<4} {'셀럽':<14} {'점수':>6} {'언급':>8} {'참여율':>7} {'감성':>6}")
        print("-"*55)
        for rank, s in enumerate(scores[:10], 1):
            icon = rank_icons.get(rank, f"  {rank}")
            profile = MOCK_PROFILES.get(s["name"], DEFAULT_PROFILE)
            print(f"{icon:<4} {s['name']:<14} {s['score']:>5.1f}  {s['mention_total']:>8,}  {s['engagement']:>6.1f}  {s['sentiment']:>5.0%}")

    # ─── 4단계: Claude AI 셀럽 프로파일 분석 ─────────────────────────────────
    print_h("④ AI 셀럽 이미지 분석 (Claude API)", style="bold yellow")

    top5 = scores[:5]
    for rank, s in enumerate(top5, 1):
        profile = MOCK_PROFILES.get(s["name"], DEFAULT_PROFILE)
        icon = rank_icons.get(rank, str(rank))
        tags_str = "  ".join(f"[{t}]" for t in profile["image_tags"])

        if console:
            top_industries = sorted(profile["industry_fit"].items(), key=lambda x: x[1], reverse=True)[:3]
            industry_str = "  ".join(f"{INDUSTRY_LABELS[k]} {v}점" for k, v in top_industries)
            console.print(Panel(
                f"[bold]{icon} {s['name']}[/bold]  {tags_str}\n\n"
                f"[dim]이미지 요약:[/dim] {profile['summary']}\n\n"
                f"[dim]TOP 3 적합 산업군:[/dim]  {industry_str}\n\n"
                f"[dim]마케팅 인사이트:[/dim] {profile['brand_fit']}",
                border_style="blue",
                width=90,
            ))
        else:
            print(f"\n{icon} {s['name']}  {tags_str}")
            print(f"   이미지 요약: {profile['summary']}")
            top3 = sorted(profile["industry_fit"].items(), key=lambda x: x[1], reverse=True)[:3]
            industry_str = " / ".join(f"{INDUSTRY_LABELS[k]} {v}점" for k, v in top3)
            print(f"   TOP 3 산업군: {industry_str}")
            print(f"   마케팅 인사이트: {profile['brand_fit']}")

    # ─── 5단계: 산업군별 추천 셀럽 ───────────────────────────────────────────
    print_h("⑤ B2C 산업군별 마케팅 최적 셀럽", style="bold magenta")

    industry_rankings: dict[str, list] = {k: [] for k in INDUSTRY_LABELS}
    for s in scores[:15]:
        profile = MOCK_PROFILES.get(s["name"], DEFAULT_PROFILE)
        for industry, fit in profile["industry_fit"].items():
            combined = s["score"] * 0.4 + fit * 0.6
            industry_rankings[industry].append((s["name"], combined, fit))

    for industry, label in INDUSTRY_LABELS.items():
        ranked = sorted(industry_rankings[industry], key=lambda x: x[1], reverse=True)[:5]
        if console:
            names_str = "  ".join(
                f"[bold cyan]{i+1}위 {n}[/]([dim]{f:.0f}점[/])" for i, (n, _, f) in enumerate(ranked)
            )
            console.print(f"  {label:<22} {names_str}")
        else:
            names_str = "  ".join(f"{i+1}위 {n}({f:.0f}점)" for i, (n, _, f) in enumerate(ranked))
            print(f"  {label:<20} {names_str}")

    # ─── 6단계: 네이버 블로그 자동 포스팅 샘플 ──────────────────────────────────
    print_h("⑥ 네이버 블로그 자동 포스팅 샘플 (Claude 생성)", style="bold magenta")

    top1 = scores[0]
    top1_profile = MOCK_PROFILES.get(top1["name"], DEFAULT_PROFILE)
    top1_industries = sorted(top1_profile["industry_fit"].items(), key=lambda x: x[1], reverse=True)[:3]

    blog_title = f"[{week_start.strftime('%Y년 %m월 %d일')} 주간] 마케팅 효과 셀럽 TOP 10 분석 — {top1['name']} 1위!"

    blog_summary = (
        f"이번 주 한국 SNS 셀럽 마케팅 분석 결과, {top1['name']}이(가) 마케팅 점수 "
        f"{top1['score']:.1f}점으로 1위를 차지했습니다. "
        f"총 {top1['mention_total']:,}건의 언급과 {top1['sentiment']:.0%}의 긍정 감성으로 "
        f"전 플랫폼에서 압도적인 존재감을 보였습니다.\n\n"
        f"■ 1위 {top1['name']} 이미지 분석\n"
        f"  키워드: {' · '.join(top1_profile['image_tags'])}\n"
        f"  {top1_profile['summary']}\n\n"
        f"■ 추천 산업군\n"
        + "\n".join(f"  {INDUSTRY_LABELS[k]} — 적합도 {v}점" for k, v in top1_industries) +
        "\n\n■ TOP 10 순위 요약\n"
        + "\n".join(
            f"  {rank}위 {s['name']} ({s['score']:.1f}점)"
            for rank, s in enumerate(scores[:10], 1)
        )
    )

    blog_tags = [top1["name"], "셀럽마케팅", "인플루언서", "마케팅분석", "SNS분석", "브랜드마케팅"]

    if console:
        console.print(Panel(
            f"[bold yellow]제목:[/] {blog_title}\n\n"
            f"[bold yellow]태그:[/] {' '.join(f'#{t}' for t in blog_tags)}\n\n"
            f"[bold yellow]본문 미리보기:[/]\n{blog_summary}",
            title="[bold]네이버 블로그 게시물 (Claude API 생성)[/]",
            border_style="magenta",
            width=90,
        ))
    else:
        print(f"\n[블로그 제목] {blog_title}")
        print(f"[태그] {' '.join(f'#{t}' for t in blog_tags)}")
        print(f"\n[본문 미리보기]\n{blog_summary}")

    # ─── 7단계: API 응답 샘플 ─────────────────────────────────────────────────
    print_h("⑦ API 응답 샘플 (/api/v1/rankings/current)", style="bold yellow")

    api_response = {
        "week_start": week_start.isoformat(),
        "rankings": [
            {
                "rank": rank,
                "celebrity_id": idx + 1,
                "name": s["name"],
                "marketing_score": s["score"],
                "mention_total": s["mention_total"],
                "engagement_rate": round(s["engagement"], 2),
                "sentiment_avg": round(s["sentiment"], 3),
                "image_tags": MOCK_PROFILES.get(s["name"], DEFAULT_PROFILE)["image_tags"][:4],
                "personality_summary": MOCK_PROFILES.get(s["name"], DEFAULT_PROFILE)["summary"][:60] + "...",
            }
            for idx, (rank, s) in enumerate(zip(range(1, 6), scores[:5]))
        ],
    }
    if console:
        console.print_json(json.dumps(api_response, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(api_response, ensure_ascii=False, indent=2))

    # ─── 완료 메시지 ──────────────────────────────────────────────────────────
    if console:
        console.print(Panel.fit(
            "[bold green]샘플 실행 완료![/]\n\n"
            "실제 서비스 시작:\n"
            "[dim]  1. cp .env.example .env  (API 키 입력)[/dim]\n"
            "[dim]  2. docker-compose up -d[/dim]\n"
            "[dim]  3. curl -X POST http://localhost:8000/api/v1/rankings/admin/trigger-update[/dim]\n"
            "[dim]  4. open http://localhost:3000[/dim]",
            border_style="green",
        ))
    else:
        print("\n" + "="*60)
        print("샘플 실행 완료!")
        print("실제 서비스: docker-compose up -d && open http://localhost:3000")
        print("="*60)


if __name__ == "__main__":
    asyncio.run(run_demo())
