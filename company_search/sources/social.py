"""Social buzz: Reddit (PRAW) for US, Naver Finance discussion board for KR."""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from .. import cache
from ..schema import CompanyDoc

UA = "Mozilla/5.0 (Linux; company-search/0.1)"

REDDIT_SUBS = ["stocks", "investing", "wallstreetbets", "SecurityAnalysis"]


@cache.cached("social:reddit", ttl=4 * 3600)
def search_reddit(company: str, limit: int = 10) -> list[dict[str, Any]]:
    cid = os.environ.get("REDDIT_CLIENT_ID")
    csec = os.environ.get("REDDIT_CLIENT_SECRET")
    ua = os.environ.get("REDDIT_USER_AGENT", "company-search/0.1")
    if not (cid and csec):
        return [{"error": "REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET not set"}]
    try:
        import praw

        reddit = praw.Reddit(client_id=cid, client_secret=csec, user_agent=ua)
        results: list[dict[str, Any]] = []
        for sub in REDDIT_SUBS:
            for post in reddit.subreddit(sub).search(company, sort="new", limit=limit // len(REDDIT_SUBS) + 1):
                doc = CompanyDoc(
                    company=company,
                    ticker=None,
                    market="US",
                    source="social",
                    url=f"https://reddit.com{post.permalink}",
                    title=post.title,
                    body_md=(post.selftext or "")[:4000],
                    published_at=datetime.utcfromtimestamp(post.created_utc),
                    metadata={
                        "subreddit": sub,
                        "score": post.score,
                        "num_comments": post.num_comments,
                    },
                )
                results.append(doc.to_dict())
                if len(results) >= limit:
                    return results
        return results
    except Exception as e:
        return [{"error": str(e)}]


@cache.cached("social:naver_board", ttl=2 * 3600)
def search_naver_board(ticker: str, limit: int = 20) -> list[dict[str, Any]]:
    """Naver Finance 종목토론방."""
    url = f"https://finance.naver.com/item/board.naver?code={ticker}"
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=15)
        r.raise_for_status()
    except Exception as e:
        return [{"error": f"naver board fetch failed: {e}"}]
    soup = BeautifulSoup(r.content, "lxml", from_encoding="euc-kr")
    docs: list[dict[str, Any]] = []
    for tr in soup.select("table.type2 tr")[:limit * 2]:
        a = tr.select_one("td.title a")
        if not a:
            continue
        title = a.get("title") or a.get_text(strip=True)
        href = a.get("href", "")
        if href and not href.startswith("http"):
            href = "https://finance.naver.com" + href
        date_cell = tr.select_one("td.gray03, td span.tah")
        date = date_cell.get_text(strip=True) if date_cell else ""
        doc = CompanyDoc(
            company=ticker,
            ticker=ticker,
            market="KR",
            source="social",
            url=href,
            title=title,
            body_md="",
            metadata={"platform": "naver_board", "posted": date},
        )
        docs.append(doc.to_dict())
        if len(docs) >= limit:
            break
    return docs


def search_social(company: str, market: str = "US", limit: int = 10) -> list[dict[str, Any]]:
    if market == "KR":
        return search_naver_board(company, limit=limit)
    return search_reddit(company, limit=limit)
