"""Company IR materials & SEC 8-K transcripts.

KR: piggyback on OpenDART recent disclosures (사업보고서, 분기·반기보고서, IR자료).
US: SEC EDGAR full-text search for 8-K with conference call transcripts.
"""

from __future__ import annotations

from typing import Any

import requests
from bs4 import BeautifulSoup

from .. import cache
from ..schema import CompanyDoc
from . import financials_kr

UA = "Mozilla/5.0 (Linux; company-search/0.1)"


@cache.cached("ir:kr", ttl=12 * 3600)
def search_ir_kr(company: str, limit: int = 5) -> list[dict[str, Any]]:
    items = financials_kr.list_recent_disclosures(company, limit=limit * 2)
    keep = []
    for it in items:
        title = it.get("title", "")
        if any(kw in title for kw in ("사업보고서", "분기보고서", "반기보고서", "IR", "실적", "기업설명회")):
            doc = CompanyDoc(
                company=company,
                ticker=None,
                market="KR",
                source="ir",
                url=it["url"],
                title=title,
                body_md="",
                metadata={"date": it.get("date", ""), "rcept_no": it.get("rcept_no", "")},
            )
            keep.append(doc.to_dict())
        if len(keep) >= limit:
            break
    return keep


@cache.cached("ir:us", ttl=12 * 3600)
def search_ir_us(ticker: str, limit: int = 5) -> list[dict[str, Any]]:
    """SEC EDGAR full-text search for 8-K filings mentioning the ticker."""
    url = (
        f"https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22"
        f"&dateRange=custom&forms=8-K"
    )
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return [{"error": str(e)}]
    hits = data.get("hits", {}).get("hits", [])[:limit]
    docs: list[dict[str, Any]] = []
    for h in hits:
        src = h.get("_source", {})
        cik = src.get("ciks", [""])[0] if src.get("ciks") else ""
        doc_url = (
            f"https://www.sec.gov/Archives/edgar/data/"
            f"{cik}/{src.get('adsh', '').replace('-', '')}/"
        )
        doc = CompanyDoc(
            company=ticker,
            ticker=ticker,
            market="US",
            source="ir",
            url=doc_url,
            title=src.get("display_names", [""])[0] if src.get("display_names") else src.get("form", ""),
            body_md="",
            metadata={"form": src.get("form", ""), "filed": src.get("file_date", "")},
        )
        docs.append(doc.to_dict())
    return docs


def search_ir(company: str, market: str = "KR", limit: int = 5) -> list[dict[str, Any]]:
    return search_ir_kr(company, limit) if market == "KR" else search_ir_us(company, limit)
