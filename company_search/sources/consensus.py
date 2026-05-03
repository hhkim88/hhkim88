"""Analyst consensus metadata (target price, recommendation distribution).

KR: scrape Naver Finance 종목분석.
US: yfinance Ticker.recommendations + analyst_price_targets.
"""

from __future__ import annotations

from typing import Any

import requests
from bs4 import BeautifulSoup

from .. import cache
from ..schema import CompanyDoc

UA = "Mozilla/5.0 (Linux; company-search/0.1)"


@cache.cached("consensus:kr", ttl=6 * 3600)
def get_consensus_kr(ticker: str) -> dict[str, Any]:
    """Pull Naver coinfo.naver page and extract consensus block."""
    url = f"https://finance.naver.com/item/coinfo.naver?code={ticker}"
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=15)
        r.raise_for_status()
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}
    soup = BeautifulSoup(r.content, "lxml", from_encoding="euc-kr")
    out: dict[str, Any] = {"ticker": ticker, "url": url}
    # Look for "투자의견" / "목표주가" labels in the page
    for em in soup.find_all(text=lambda t: t and ("투자의견" in t or "목표주가" in t)):
        parent = em.parent
        if parent is None:
            continue
        label = em.strip()
        sibling = parent.find_next("em") or parent.find_next("strong") or parent.find_next("span")
        if sibling:
            out[label] = sibling.get_text(strip=True)
    # Fallback: dump tables containing 'consensus' or '의견'
    out["raw_html_excerpt"] = r.text[:2000]
    return out


@cache.cached("consensus:us", ttl=6 * 3600)
def get_consensus_us(ticker: str) -> dict[str, Any]:
    try:
        import yfinance as yf

        t = yf.Ticker(ticker)
        info = t.info or {}
        consensus = {
            "ticker": ticker,
            "recommendationKey": info.get("recommendationKey"),
            "recommendationMean": info.get("recommendationMean"),
            "numberOfAnalystOpinions": info.get("numberOfAnalystOpinions"),
            "targetMeanPrice": info.get("targetMeanPrice"),
            "targetHighPrice": info.get("targetHighPrice"),
            "targetLowPrice": info.get("targetLowPrice"),
            "targetMedianPrice": info.get("targetMedianPrice"),
            "currentPrice": info.get("currentPrice"),
        }
        # Recommendation history
        try:
            recs = t.recommendations
            if recs is not None and not recs.empty:
                consensus["recent_recommendations"] = recs.tail(10).to_dict(orient="records")
        except Exception:
            pass
        return consensus
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}


def get_consensus(ticker_or_name: str, market: str = "KR") -> dict[str, Any]:
    if market == "KR":
        return get_consensus_kr(ticker_or_name)
    return get_consensus_us(ticker_or_name)
