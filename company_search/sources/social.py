"""Social buzz: Reddit (PRAW or public-JSON fallback) for US, Naver Finance
discussion board for KR.

Reddit's PRAW path needs REDDIT_CLIENT_ID/SECRET, and the "create app" form
errors out for many users (regional restrictions, captcha loops, new-account
karma gates). When credentials are absent or PRAW fails, fall back to Reddit's
public JSON search endpoints — same quality as PRAW (full body, score, comment
count), no auth required, just needs a custom User-Agent. The earlier Google
News fallback was abandoned because Google News is a curated news aggregator
and almost never indexes reddit.com threads, so the fallback returned 0 items.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .. import cache
from .._http import get_html
from ..schema import CompanyDoc

REDDIT_SUBS = ["stocks", "investing", "wallstreetbets", "SecurityAnalysis"]


def _reddit_via_public_json(company: str, limit: int) -> list[dict[str, Any]]:
    """Reddit search via reddit.com/r/<sub>/search.json (no auth required).

    The unauthenticated JSON endpoint enforces a polite User-Agent; the default
    python-requests UA is rate-limited aggressively. With a real UA the limits
    are roughly 10 req/min per IP, which the 4-hour cache TTL absorbs easily.
    """
    ua = os.environ.get("REDDIT_USER_AGENT", "company-search/0.1 (debate)")
    headers = {"User-Agent": ua}
    docs: list[dict[str, Any]] = []
    per_sub = max(2, limit // len(REDDIT_SUBS) + 1)
    for sub in REDDIT_SUBS:
        url = f"https://www.reddit.com/r/{sub}/search.json"
        params = {"q": company, "restrict_sr": "1", "sort": "new", "limit": per_sub}
        try:
            r = requests.get(url, headers=headers, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
        except Exception:
            # Silently skip a single subreddit failure — we still want partial
            # coverage from the others rather than aborting the whole pool.
            continue
        for child in data.get("data", {}).get("children", []):
            post = child.get("data", {}) or {}
            title = (post.get("title") or "").strip()
            if not title:
                continue
            permalink = post.get("permalink") or ""
            full_url = f"https://reddit.com{permalink}" if permalink else (post.get("url") or "")
            created = post.get("created_utc")
            published = (
                datetime.utcfromtimestamp(created) if isinstance(created, (int, float)) else None
            )
            doc = CompanyDoc(
                company=company,
                ticker=None,
                market="US",
                source="social",
                url=full_url,
                title=title,
                body_md=(post.get("selftext") or "")[:4000],
                published_at=published,
                metadata={
                    "platform": "reddit_public_json",
                    "subreddit": sub,
                    "publisher": f"r/{sub}",
                    "score": post.get("score", 0),
                    "num_comments": post.get("num_comments", 0),
                },
            )
            docs.append(doc.to_dict())
            if len(docs) >= limit:
                return docs
    return docs


@cache.cached("social:reddit:v4", ttl=4 * 3600)
def search_reddit(company: str, limit: int = 10) -> list[dict[str, Any]]:
    cid = os.environ.get("REDDIT_CLIENT_ID")
    csec = os.environ.get("REDDIT_CLIENT_SECRET")
    ua = os.environ.get("REDDIT_USER_AGENT", "company-search/0.1")
    if not (cid and csec):
        # No keys → use the public JSON fallback so the social pool isn't
        # silently empty for users who can't get a Reddit script app issued.
        return _reddit_via_public_json(company, limit=limit)
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
                        "platform": "reddit_praw",
                        "subreddit": sub,
                        "publisher": f"r/{sub}",
                        "score": post.score,
                        "num_comments": post.num_comments,
                    },
                )
                results.append(doc.to_dict())
                if len(results) >= limit:
                    return results
        if results:
            return results
        # PRAW returned nothing (rare — usually means the search rate-limited).
        # Fall through to the public-JSON path.
        return _reddit_via_public_json(company, limit=limit)
    except Exception:
        # Any PRAW-level failure (auth revoked, rate limit, network) — fall
        # back rather than poisoning the pool with an error doc.
        return _reddit_via_public_json(company, limit=limit)


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
