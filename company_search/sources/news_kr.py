"""Korean news search.

Three layered fetch strategies, each tried in order until one returns items:

1. Naver Open API (cleanest; needs NAVER_CLIENT_ID + NAVER_CLIENT_SECRET).
2. Google News RSS with hl=ko / gl=KR / ceid=KR:ko (no key needed).
3. Naver search scrape with realistic browser headers and multiple
   selectors for forward/backward HTML compatibility.

Body extraction still goes through newspaper4k. If the article body comes
back empty (paywall / JS-only) we fall back to the source's own snippet so
the agent always has *something* to quote.
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any
from urllib.parse import quote

import feedparser
import requests
from bs4 import BeautifulSoup

from .. import cache
from .._http import browser_headers, get_html
from ..schema import CompanyDoc

BULL_TERMS = ["호실적", "성장", "수주", "어닝 서프라이즈", "목표가 상향", "신고가", "최대 실적"]
BEAR_TERMS = ["부진", "리스크", "어닝 쇼크", "목표가 하향", "소송", "감사", "급락", "적자"]


def _build_query(company: str, stance: str) -> str:
    if stance == "bull":
        return f"{company} ({' OR '.join(BULL_TERMS)})"
    if stance == "bear":
        return f"{company} ({' OR '.join(BEAR_TERMS)})"
    return company


def _strip_html(s: str) -> str:
    return (
        s.replace("<b>", "")
        .replace("</b>", "")
        .replace("&quot;", '"')
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )


def _via_naver_api(query: str, limit: int) -> list[dict[str, Any]]:
    cid = os.environ.get("NAVER_CLIENT_ID", "").strip()
    csec = os.environ.get("NAVER_CLIENT_SECRET", "").strip()
    if not (cid and csec):
        return []
    r = requests.get(
        "https://openapi.naver.com/v1/search/news.json",
        params={"query": query, "display": min(limit * 2, 100), "sort": "date"},
        headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": csec},
        timeout=15,
    )
    r.raise_for_status()
    items: list[dict[str, Any]] = []
    for it in r.json().get("items", [])[:limit]:
        link = it.get("originallink") or it.get("link", "")
        items.append(
            {
                "title": _strip_html(it.get("title", "")),
                "url": link,
                "snippet": _strip_html(it.get("description", "")),
                "pub_date": it.get("pubDate"),
            }
        )
    return items


def _via_google_news_rss(query: str, limit: int) -> list[dict[str, Any]]:
    url = (
        f"https://news.google.com/rss/search?q={quote(query)}"
        f"&hl=ko&gl=KR&ceid=KR:ko"
    )
    r = requests.get(url, headers=browser_headers(), timeout=15)
    r.raise_for_status()
    feed = feedparser.parse(r.content)
    items: list[dict[str, Any]] = []
    for entry in feed.entries[:limit]:
        items.append(
            {
                "title": getattr(entry, "title", "").strip(),
                "url": getattr(entry, "link", "").strip(),
                "snippet": getattr(entry, "summary", "").strip(),
                "pub_date": getattr(entry, "published", None),
            }
        )
    return [it for it in items if it["title"] and it["url"].startswith("http")]


def _via_naver_scrape(query: str, limit: int) -> list[dict[str, Any]]:
    url = (
        "https://search.naver.com/search.naver"
        f"?where=news&query={quote(query)}&sort=1"
    )
    r = get_html(url, referer="https://www.naver.com/")
    soup = BeautifulSoup(r.text, "lxml")
    # Multiple selectors — Naver rotates its search markup
    blocks = (
        soup.select("ul.list_news li.bx")
        or soup.select("div.news_area")
        or soup.select("li.bx")
        or soup.select("div.group_news ul.list_news li")
        or soup.select("section.sc_new ul li")
    )
    items: list[dict[str, Any]] = []
    for block in blocks:
        a = (
            block.select_one("a.news_tit")
            or block.select_one("a.tit")
            or block.select_one("a.news_contents")
            or block.find("a")
        )
        if not a or not a.get("href"):
            continue
        title = (a.get("title") or a.get_text(strip=True) or "").strip()
        href = a["href"]
        if not title or not href.startswith("http"):
            continue
        items.append({"title": title, "url": href, "snippet": "", "pub_date": None})
        if len(items) >= limit:
            break
    return items


def _parse_pub_date(raw: Any) -> datetime | None:
    if isinstance(raw, datetime):
        return raw
    if not isinstance(raw, str):
        return None
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S"):
        try:
            return datetime.strptime(raw[:31], fmt)
        except ValueError:
            continue
    return None


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
    items: list[dict[str, Any]] = []
    errors: list[str] = []

    for label, fn in (
        ("naver_api", _via_naver_api),
        ("google_news_rss", _via_google_news_rss),
        ("naver_scrape", _via_naver_scrape),
    ):
        try:
            items = fn(query, limit)
        except Exception as e:
            errors.append(f"{label}: {e}")
            items = []
        if items:
            break

    if not items:
        return [{"error": " | ".join(errors) or "no items found"}]

    out: list[dict[str, Any]] = []
    for it in items:
        time.sleep(0.4)
        body, pub = _extract_body(it["url"])
        if not body:
            body = it.get("snippet", "")
        if not pub:
            pub = _parse_pub_date(it.get("pub_date"))
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
