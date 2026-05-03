"""Lightweight sentiment scoring. Returns float in [-1.0, 1.0]."""

from __future__ import annotations

from functools import lru_cache

KO_POS = {
    "성장", "호실적", "수주", "최대", "신고가", "상향", "흑자", "어닝서프라이즈",
    "강세", "확대", "투자", "기대", "긍정", "수익", "개선", "돌파", "급등",
}
KO_NEG = {
    "부진", "리스크", "쇼크", "하향", "소송", "감사", "급락", "적자", "손실",
    "하락", "약세", "위기", "부정", "축소", "지연", "경고", "악화",
}


@lru_cache(maxsize=1)
def _vader():
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

    return SentimentIntensityAnalyzer()


def score(text: str, lang: str = "auto") -> float:
    if not text:
        return 0.0
    if lang == "auto":
        lang = "ko" if any("가" <= c <= "힣" for c in text[:200]) else "en"
    if lang == "en":
        return _vader().polarity_scores(text[:5000])["compound"]
    sample = text[:3000]
    pos = sum(1 for w in KO_POS if w in sample)
    neg = sum(1 for w in KO_NEG if w in sample)
    if pos + neg == 0:
        return 0.0
    return (pos - neg) / (pos + neg)


def attach(docs: list[dict]) -> list[dict]:
    for d in docs:
        if d.get("sentiment") is None:
            d["sentiment"] = score(d.get("body_md", "") + " " + d.get("title", ""))
    return docs
