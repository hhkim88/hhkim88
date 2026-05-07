"""Earnings call transcripts.

US: Motley Fool publishes free full-text earnings call transcripts at
fool.com/earnings/call-transcripts/. We discover them through Google News
RSS with a `site:fool.com` filter, then fetch the page body with newspaper4k
to capture the actual transcript text.

KR: there is no equivalent free transcript source. Korean firms post
earnings call recordings/scripts on their IR pages but rarely publish
transcribed text. Returns an empty list with an explanatory error so the
caller can surface the gap.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any
from urllib.parse import quote

import feedparser

from .. import cache
from ..schema import CompanyDoc

# Free transcript publishers. Motley Fool covers most US large-caps quarterly.
# Seeking Alpha hosts transcripts too but paywalls the body, so we don't list
# it here — get_seeking_alpha covers their headline coverage separately.
US_TRANSCRIPT_HOSTS = ("fool.com",)


def _extract_body(url: str) -> tuple[str, Any]:
    try:
        from newspaper import Article

        art = Article(url, language="en")
        art.download()
        art.parse()
        return art.text or "", art.publish_date
    except Exception:
        return "", None


@cache.cached("earnings_call:us", ttl=24 * 3600)
def search_earnings_calls_us(company: str, limit: int = 5) -> list[dict[str, Any]]:
    site_filter = " OR ".join(f"site:{h}" for h in US_TRANSCRIPT_HOSTS)
    q = f'"{company}" earnings call transcript ({site_filter})'
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
        # Reject items that are clearly previews/news about the call rather
        # than the transcript itself. Transcript pages on Motley Fool always
        # contain "transcript" in the URL or title.
        if "transcript" not in (url + " " + title).lower():
            continue
        time.sleep(0.4)
        body, pub = _extract_body(url)
        published = None
        if entry.get("published_parsed"):
            published = datetime(*entry.published_parsed[:6])
        # Truncate aggressively — full transcripts are 50–100k chars, but the
        # MCP collect-pool budget is small. 12k chars is enough for the agent
        # to extract a couple of CFO/CEO quotes.
        doc = CompanyDoc(
            company=company,
            ticker=None,
            market="US",
            source="earnings_call",
            url=url,
            title=title,
            body_md=body[:12000] or entry.get("summary", "")[:800],
            published_at=pub or published,
            metadata={
                "platform": "motley_fool",
                "publisher": entry.get("source", {}).get("title", "Motley Fool"),
            },
        )
        docs.append(doc.to_dict())
        if len(docs) >= limit:
            break
    return docs


def search_earnings_calls(
    company: str, market: str = "US", limit: int = 5
) -> list[dict[str, Any]]:
    if market == "US":
        return search_earnings_calls_us(company, limit=limit)
    return [
        {
            "error": (
                "KR equivalent of free earnings call transcripts not available. "
                "Korean firms post recordings on IR pages but rarely publish "
                "transcribed text. Use get_ir_materials for filings instead."
            )
        }
    ]
