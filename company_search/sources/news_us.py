"""US news search via Google News RSS + body extraction via newspaper4k."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote

import feedparser

from .. import cache
from ..schema import CompanyDoc

BULL_TERMS = ["growth", "beat estimates", "upgrade", "price target raised", "record earnings"]
BEAR_TERMS = ["lawsuit", "miss", "downgrade", "price target cut", "decline", "loss", "risk"]


def _build_query(company: str, stance: str) -> str:
    if stance == "bull":
        return f'"{company}" ({" OR ".join(BULL_TERMS)})'
    if stance == "bear":
        return f'"{company}" ({" OR ".join(BEAR_TERMS)})'
    return f'"{company}"'


def _extract_body(url: str) -> tuple[str, Any]:
    try:
        from newspaper import Article

        art = Article(url, language="en")
        art.download()
        art.parse()
        return art.text or "", art.publish_date
    except Exception:
        return "", None


@cache.cached("news_us", ttl=6 * 3600)
def search_news_us(
    company: str, stance: str = "neutral", limit: int = 5
) -> list[dict[str, Any]]:
    q = _build_query(company, stance)
    feed_url = f"https://news.google.com/rss/search?q={quote(q)}&hl=en-US&gl=US&ceid=US:en"
    feed = feedparser.parse(feed_url)
    out: list[dict[str, Any]] = []
    for entry in feed.entries[:limit]:
        time.sleep(0.4)
        url = entry.get("link", "")
        title = entry.get("title", "")
        body, pub = _extract_body(url)
        published = None
        if entry.get("published_parsed"):
            from datetime import datetime

            published = datetime(*entry.published_parsed[:6])
        doc = CompanyDoc(
            company=company,
            ticker=None,
            market="US",
            source="news",
            url=url,
            title=title,
            body_md=body[:8000] or entry.get("summary", "")[:1000],
            published_at=pub or published,
            metadata={"stance_filter": stance, "feed_source": entry.get("source", {}).get("title", "")},
        )
        out.append(doc.to_dict())
    return out
