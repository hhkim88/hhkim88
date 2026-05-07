"""Seeking Alpha analyst commentary (US only).

SA hosts thousands of contributor articles ranging from quant analysis to
contrarian opinion pieces — exactly the "actually-circulating arguments"
the debate orchestrator wants. Direct scraping is unreliable (Cloudflare
+ paywall after 1 article/day for non-subscribers), so we route through
Google News RSS with a `site:seekingalpha.com` filter. This gives us
headlines, snippets, and direct article URLs; the snippet is usually
enough for the debate agent to identify the bull/bear thesis being
referenced.

KR equivalent (e.g., Kakao Stock community articles): not implemented
because the existing Naver 종토방 scraper in social.py already covers
retail commentary on Korean tickers.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any
from urllib.parse import quote

import feedparser

from .. import cache
from ..schema import CompanyDoc

# Direct page fetch on seekingalpha.com almost always returns either a
# Cloudflare challenge or a teaser stub. Stick to Google News headlines
# and the entry summary, which Google often pre-extracts.
SA_DOMAIN = "seekingalpha.com"


def _expand_query(company: str, stance: str) -> str:
    base = f'"{company}" site:{SA_DOMAIN}'
    if stance == "bull":
        return f"{base} (bullish OR upgrade OR buy OR undervalued)"
    if stance == "bear":
        return f"{base} (bearish OR downgrade OR sell OR overvalued OR risk)"
    return base


@cache.cached("seekingalpha:us:v1", ttl=12 * 3600)
def search_seeking_alpha(
    company: str, stance: str = "neutral", limit: int = 5
) -> list[dict[str, Any]]:
    q = _expand_query(company, stance)
    feed_url = (
        "https://news.google.com/rss/search"
        f"?q={quote(q)}&hl=en-US&gl=US&ceid=US:en"
    )
    feed = feedparser.parse(feed_url)
    docs: list[dict[str, Any]] = []
    for entry in feed.entries[: limit * 2]:
        url = entry.get("link", "")
        title = entry.get("title", "")
        if not url or not title:
            continue
        if SA_DOMAIN not in url and SA_DOMAIN not in (entry.get("source", {}).get("href") or ""):
            # Google sometimes returns a related article from another outlet
            # — skip if it isn't an actual seekingalpha.com link.
            continue
        time.sleep(0.3)
        published = None
        if entry.get("published_parsed"):
            published = datetime(*entry.published_parsed[:6])
        # SA full body almost always Cloudflare-blocked, so use the
        # Google News-provided summary as the snippet body.
        snippet = entry.get("summary", "") or ""
        doc = CompanyDoc(
            company=company,
            ticker=None,
            market="US",
            source="seeking_alpha",
            url=url,
            title=title,
            body_md=snippet[:4000],
            published_at=published,
            metadata={
                "platform": "seeking_alpha",
                "publisher": "Seeking Alpha",
                "stance_filter": stance,
            },
        )
        docs.append(doc.to_dict())
        if len(docs) >= limit:
            break
    return docs
