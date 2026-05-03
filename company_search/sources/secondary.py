"""Second-hand citation news.

Newspapers report '○○증권 목표가 상향' style summaries of paywalled analyst reports.
We piggyback on news_kr / news_us with broker-keyword expanded queries.
"""

from __future__ import annotations

from typing import Any

from . import news_kr, news_us

KR_BROKER_KEYWORDS = [
    "증권", "리포트", "목표주가", "목표가", "투자의견", "매수", "매도", "비중확대",
]
US_BROKER_KEYWORDS = [
    "Goldman", "Morgan Stanley", "JPMorgan", "Citi", "Wells Fargo", "BofA",
    "price target", "upgrade", "downgrade", "Strong Buy", "Sell rating",
]


def search_kr(company: str, limit: int = 10) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for kw in ("목표주가", "투자의견", "목표가 상향", "목표가 하향"):
        out = news_kr.search_news_kr(f"{company} {kw}", stance="neutral", limit=max(2, limit // 4))
        for d in out:
            d.setdefault("metadata", {})["broker_keyword"] = kw
            d["source"] = "report"
        docs.extend(out)
        if len(docs) >= limit:
            break
    return docs[:limit]


def search_us(company: str, limit: int = 10) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for kw in ("price target", "analyst upgrade", "analyst downgrade"):
        out = news_us.search_news_us(f"{company} {kw}", stance="neutral", limit=max(2, limit // 3))
        for d in out:
            d.setdefault("metadata", {})["broker_keyword"] = kw
            d["source"] = "report"
        docs.extend(out)
        if len(docs) >= limit:
            break
    return docs[:limit]


def search_secondary(company: str, market: str = "KR", limit: int = 10) -> list[dict[str, Any]]:
    return search_kr(company, limit) if market == "KR" else search_us(company, limit)
