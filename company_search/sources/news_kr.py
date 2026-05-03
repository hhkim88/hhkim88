"""Korean news search via Naver News + body extraction via newspaper4k."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from .. import cache
from ..schema import CompanyDoc

UA = "Mozilla/5.0 (Linux; company-search/0.1)"

BULL_TERMS = ["호실적", "성장", "수주", "어닝 서프라이즈", "목표가 상향", "신고가", "최대 실적"]
BEAR_TERMS = ["부진", "리스크", "어닝 쇼크", "목표가 하향", "소송", "감사", "급락", "적자"]


def _build_query(company: str, stance: str) -> str:
    if stance == "bull":
        return f"{company} ({' OR '.join(BULL_TERMS)})"
    if stance == "bear":
        return f"{company} ({' OR '.join(BEAR_TERMS)})"
    return company


def _search_naver_news(query: str, limit: int) -> list[dict[str, str]]:
    url = f"https://search.naver.com/search.naver?where=news&query={quote(query)}&sort=1"
    r = requests.get(url, headers={"User-Agent": UA}, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    items: list[dict[str, str]] = []
    for li in soup.select("ul.list_news li.bx, div.news_area"):
        a = li.select_one("a.news_tit") or li.select_one("a.news_contents") or li.find("a")
        if not a or not a.get("href"):
            continue
        title = (a.get("title") or a.get_text(strip=True) or "").strip()
        href = a["href"]
        if not title or not href.startswith("http"):
            continue
        items.append({"title": title, "url": href})
        if len(items) >= limit:
            break
    return items


def _extract_body(url: str) -> tuple[str, datetime | None]:
    try:
        from newspaper import Article

        art = Article(url, language="ko")
        art.download()
        art.parse()
        return art.text or "", art.publish_date
    except Exception:
        return "", None


@cache.cached("news_kr", ttl=6 * 3600)
def search_news_kr(
    company: str, stance: str = "neutral", limit: int = 5
) -> list[dict[str, Any]]:
    query = _build_query(company, stance)
    items = _search_naver_news(query, limit=limit)
    out: list[dict[str, Any]] = []
    for it in items:
        time.sleep(0.5)
        body, pub = _extract_body(it["url"])
        doc = CompanyDoc(
            company=company,
            ticker=None,
            market="KR",
            source="news",
            url=it["url"],
            title=it["title"],
            body_md=body[:8000],
            published_at=pub,
            metadata={"stance_filter": stance},
        )
        out.append(doc.to_dict())
    return out
