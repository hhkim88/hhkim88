"""Social buzz: Reddit (PRAW) for US, Naver Finance discussion board for KR."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .. import cache
from .._http import get_html
from ..schema import CompanyDoc

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
            for post in reddit.subreddit(sub).search(
                company, sort="new", limit=limit // len(REDDIT_SUBS) + 1
            ):
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


def _via_naver_mobile_board(ticker: str, limit: int) -> list[dict[str, Any]]:
    """Mobile Naver Stock discussion page (m.stock.naver.com).
    Mobile site is a React SSR; the rendered list items are still in the
    initial HTML, but the markup changes often, so we try a pile of
    selectors before giving up."""
    url = f"https://m.stock.naver.com/domestic/stock/{ticker}/discuss"
    r = get_html(
        url,
        mobile=True,
        referer=f"https://m.stock.naver.com/domestic/stock/{ticker}",
    )
    soup = BeautifulSoup(r.content, "lxml")
    docs: list[dict[str, Any]] = []
    blocks = (
        soup.select("li.DiscussList_item")
        or soup.select("ul.DiscussList_list li")
        or soup.select("article")
        or soup.select("li.item")
        or soup.select("div.list_item")
    )
    for block in blocks:
        title_el = (
            block.select_one("strong.title")
            or block.select_one("h3")
            or block.select_one(".item_title")
            or block.select_one("p.subject")
        )
        title = title_el.get_text(strip=True) if title_el else ""
        a = block.find("a")
        href = a["href"] if a and a.get("href") else ""
        if href and not href.startswith("http"):
            href = urljoin("https://m.stock.naver.com", href)
        date_el = (
            block.select_one(".date")
            or block.select_one("time")
            or block.select_one("span.tah")
        )
        date = date_el.get_text(strip=True) if date_el else ""
        if not title:
            continue
        docs.append(
            CompanyDoc(
                company=ticker,
                ticker=ticker,
                market="KR",
                source="social",
                url=href,
                title=title,
                body_md="",
                metadata={"platform": "naver_mobile_board", "posted": date},
            ).to_dict()
        )
        if len(docs) >= limit:
            break
    return docs


def _via_naver_desktop_board(ticker: str, limit: int) -> list[dict[str, Any]]:
    url = f"https://finance.naver.com/item/board.naver?code={ticker}"
    r = get_html(url, referer="https://finance.naver.com/")
    # Try utf-8 first; fall back to euc-kr if it looks corrupted
    soup = BeautifulSoup(r.content, "lxml", from_encoding="euc-kr")
    docs: list[dict[str, Any]] = []
    for tr in soup.select("table.type2 tr")[: limit * 2]:
        a = tr.select_one("td.title a")
        if not a:
            continue
        title = a.get("title") or a.get_text(strip=True)
        href = a.get("href", "")
        if href and not href.startswith("http"):
            href = "https://finance.naver.com" + href
        date_cell = tr.select_one("td.gray03, td span.tah")
        date = date_cell.get_text(strip=True) if date_cell else ""
        docs.append(
            CompanyDoc(
                company=ticker,
                ticker=ticker,
                market="KR",
                source="social",
                url=href,
                title=title,
                body_md="",
                metadata={"platform": "naver_board", "posted": date},
            ).to_dict()
        )
        if len(docs) >= limit:
            break
    return docs


@cache.cached("social:naver_board", ttl=2 * 3600)
def search_naver_board(ticker: str, limit: int = 20) -> list[dict[str, Any]]:
    """Naver Finance 종목토론방. Mobile site first (more permissive headers
    treatment), desktop EUC-KR HTML as a fallback."""
    errors: list[str] = []
    for label, fn in (
        ("mobile", _via_naver_mobile_board),
        ("desktop", _via_naver_desktop_board),
    ):
        try:
            docs = fn(ticker, limit)
        except Exception as e:
            errors.append(f"{label}: {e}")
            docs = []
        if docs:
            return docs
    return [{"error": " | ".join(errors) or "naver board: no posts parsed"}]


def search_social(company: str, market: str = "US", limit: int = 10) -> list[dict[str, Any]]:
    if market == "KR":
        return search_naver_board(company, limit=limit)
    return search_reddit(company, limit=limit)
