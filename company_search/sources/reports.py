"""Public Korean analyst reports — Naver Finance Research + Hankyung Consensus.

Two complementary aggregators are queried and the results are merged
(deduped by URL):

1. **Naver Finance Research** — finance.naver.com/research/company_list.naver
   PDF download links sit one click from the listing. Best yield for most
   covered tickers.

2. **Hankyung Consensus** — consensus.hankyung.com
   Older aggregator with its own brokerage feed. Site has been migrated
   repeatedly so we try several known URL patterns and parse with multiple
   selectors. If the site itself is unreachable we fall back to a Naver web
   search restricted to ``site:consensus.hankyung.com``, which surfaces the
   same documents through a different door.
"""

from __future__ import annotations

import io
import re
from typing import Any
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

from .. import cache
from .._http import browser_headers, get_html
from ..schema import CompanyDoc

HANKYUNG_BASE = "https://consensus.hankyung.com"
NAVER_FIN_BASE = "https://finance.naver.com"
_LIST_URLS = (
    HANKYUNG_BASE + "/analysis/list?keyword={q}",
    HANKYUNG_BASE + "/search?keyword={q}",
    HANKYUNG_BASE + "/apps.analysis/analysis.list?search_text={q}",
)


def _extract_pdf(url: str, *, referer: str | None = None) -> str:
    """Download a PDF and pull its text. Empty string on any failure."""
    try:
        r = requests.get(
            url,
            headers=browser_headers(referer=referer or HANKYUNG_BASE + "/"),
            timeout=30,
        )
        r.raise_for_status()
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(r.content))
        text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
        return text[:12000]
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Helper: ticker resolution (name -> 6-digit KRX code)
# Naver Research's listing URL keys on ticker, not company name. We reuse the
# DART corp_code index (already cached for the financials module) to translate.
# ---------------------------------------------------------------------------

_TICKER_RE = re.compile(r"^\d{6}$")


def _ticker_from_name(name: str) -> str | None:
    """Best-effort ticker lookup. Returns None when DART is unavailable."""
    if not name:
        return None
    if _TICKER_RE.match(name.strip()):
        return name.strip()
    try:
        from .financials_kr import _corp_code_index
    except Exception:
        return None
    try:
        idx = _corp_code_index()
    except Exception:
        return None
    info = idx.get(name)
    if info and info.get("stock_code"):
        return info["stock_code"]
    # Substring fallback (handles "삼성전자(005930)" style queries)
    for cand_name, cand_info in idx.items():
        if not cand_info.get("stock_code"):
            continue
        if name in cand_name or cand_name in name:
            return cand_info["stock_code"]
    return None


# ---------------------------------------------------------------------------
# Source A: Naver Finance Research
# ---------------------------------------------------------------------------


def _via_naver_research(company: str, limit: int) -> list[dict[str, Any]]:
    """Scrape finance.naver.com/research/company_list.naver?itemCode=<ticker>.

    Each table row exposes title / brokerage / author / date and an attached
    PDF (when the brokerage permitted distribution). Naver finance is still
    served as EUC-KR for legacy reasons, so the BeautifulSoup parser is told
    to assume that encoding.
    """
    ticker = _ticker_from_name(company)
    if not ticker:
        return []
    listing_url = (
        f"{NAVER_FIN_BASE}/research/company_list.naver"
        f"?searchType=itemCode&itemCode={ticker}"
    )
    r = get_html(listing_url, referer=NAVER_FIN_BASE + "/research/")
    soup = BeautifulSoup(r.content, "lxml", from_encoding="euc-kr")

    docs: list[dict[str, Any]] = []
    # Naver finance tables vary across sections; try the common ones in order.
    rows = (
        soup.select("table.type_1 tr")
        or soup.select("table.type_5 tr")
        or soup.select("table tr")
    )
    for tr in rows[: limit * 4]:
        cells = tr.select("td")
        if len(cells) < 4:
            continue
        # Title link is usually the second column's anchor
        title_a = (
            tr.select_one("td a[href*='company_read']")
            or tr.select_one("td.title a")
            or tr.select_one("a[href*='nid=']")
        )
        if not title_a:
            continue
        title = (title_a.get("title") or title_a.get_text(strip=True) or "").strip()
        if not title or len(title) < 3:
            continue
        detail_href = title_a.get("href", "").strip()
        detail_url = (
            urljoin(NAVER_FIN_BASE + "/research/", detail_href) if detail_href else listing_url
        )

        # PDF lives in the file column — try a couple of selector shapes
        pdf_url = None
        pdf_a = tr.select_one("td a[href$='.pdf'], a[href*='download'], a[href*='pdf']")
        if pdf_a:
            href = pdf_a.get("href", "").strip()
            if href.startswith("http"):
                pdf_url = href
            elif href.startswith("/"):
                pdf_url = NAVER_FIN_BASE + href

        # Best-effort column extraction (broker / date)
        # Naver finance research listing columns are typically:
        #   종목명(0) | 제목(1) | 증권사(2) | 첨부(3) | 작성일(4) | 조회수(5)
        broker = ""
        date = ""
        cell_texts = [c.get_text(strip=True) for c in cells]
        # Skip the title and the company-name filter cell to avoid picking
        # the company itself as the brokerage.
        text_pool = [t for t in cell_texts if t and t != title and t != company]
        # Date pattern (YY.MM.DD or YYYY.MM.DD)
        for t in text_pool:
            if re.match(r"^\d{2,4}[.\-/]\d{1,2}[.\-/]\d{1,2}$", t):
                date = t
                break
        # Prefer the canonical broker column when the table has enough cells.
        if len(cells) >= 4:
            cand = cells[2].get_text(strip=True)
            if cand and cand != title and cand != company and re.search(r"[가-힣]", cand):
                broker = cand
        # Fallback heuristic: cell with Korean chars, no long digit run, and
        # not the company name or title.
        if not broker:
            for t in text_pool:
                if t == date:
                    continue
                if re.search(r"[가-힣]", t) and not re.search(r"\d{4,}", t):
                    broker = t
                    break

        body = _extract_pdf(pdf_url, referer=listing_url) if pdf_url else ""
        docs.append(
            CompanyDoc(
                company=company,
                ticker=ticker,
                market="KR",
                source="report",
                url=pdf_url or detail_url,
                title=title,
                body_md=body,
                metadata={
                    "broker": broker,
                    "report_date": date,
                    "platform": "naver_research",
                    "publisher": broker,  # so source_name surfaces the brokerage
                },
            ).to_dict()
        )
        if len(docs) >= limit:
            break
    return docs


# ---------------------------------------------------------------------------
# Source B: Hankyung Consensus (existing)
# ---------------------------------------------------------------------------


def _parse_listing(soup: BeautifulSoup, company: str, limit: int) -> list[dict[str, Any]]:
    """Parse a Hankyung listing page using several candidate row layouts."""
    rows = (
        soup.select("table tr")
        or soup.select("ul li")
        or soup.select("div.list-item")
        or soup.select("div.report-item")
    )
    docs: list[dict[str, Any]] = []
    for row in rows[: limit * 4]:
        a = row.select_one("a[href]")
        if not a:
            continue
        href = a.get("href", "").strip()
        if not href:
            continue
        title = a.get("title") or a.get_text(strip=True)
        if not title or len(title) < 3:
            continue
        full_url = urljoin(HANKYUNG_BASE, href)
        # PDF link is usually a sibling anchor in the same row
        pdf_a = row.select_one("a[href$='.pdf'], a[href*='download'], a[href*='pdf']")
        pdf_url = urljoin(HANKYUNG_BASE, pdf_a["href"]) if pdf_a else None
        body = _extract_pdf(pdf_url) if pdf_url else ""
        cells = row.select("td")
        broker = cells[1].get_text(strip=True) if len(cells) > 1 else ""
        date = cells[-1].get_text(strip=True) if cells else ""
        docs.append(
            CompanyDoc(
                company=company,
                ticker=None,
                market="KR",
                source="report",
                url=pdf_url or full_url,
                title=title,
                body_md=body,
                metadata={
                    "broker": broker,
                    "report_date": date,
                    "platform": "hankyung",
                    "publisher": broker,
                },
            ).to_dict()
        )
        if len(docs) >= limit:
            break
    return docs


def _via_hankyung_direct(company: str, limit: int) -> list[dict[str, Any]]:
    last_err: Exception | None = None
    for tmpl in _LIST_URLS:
        url = tmpl.format(q=quote(company))
        try:
            r = get_html(url, referer=HANKYUNG_BASE + "/")
        except Exception as e:
            last_err = e
            continue
        soup = BeautifulSoup(r.text, "lxml")
        docs = _parse_listing(soup, company, limit)
        if docs:
            return docs
    if last_err:
        raise last_err
    return []


def _via_naver_site_filter(company: str, limit: int) -> list[dict[str, Any]]:
    """Fallback: ask Naver Web for everything on consensus.hankyung.com.
    Many results are PDFs that can be downloaded directly."""
    query = f"{company} site:consensus.hankyung.com"
    url = (
        "https://search.naver.com/search.naver"
        f"?where=web&query={quote(query)}"
    )
    r = get_html(url, referer="https://www.naver.com/")
    soup = BeautifulSoup(r.text, "lxml")
    seen: set[str] = set()
    docs: list[dict[str, Any]] = []
    selectors = (
        "a.link_tit",
        "a.api_txt_lines",
        "h3 a",
        "div.total_wrap a.api_txt_lines",
        "li.bx a",
    )
    for sel in selectors:
        for a in soup.select(sel):
            href = a.get("href", "")
            if not href.startswith("http") or "hankyung.com" not in href:
                continue
            if href in seen:
                continue
            seen.add(href)
            title = a.get_text(strip=True)
            if not title:
                continue
            body = _extract_pdf(href) if href.lower().endswith(".pdf") else ""
            docs.append(
                CompanyDoc(
                    company=company,
                    ticker=None,
                    market="KR",
                    source="report",
                    url=href,
                    title=title,
                    body_md=body,
                    metadata={
                        "broker": "",
                        "report_date": "",
                        "platform": "hankyung_via_naver",
                    },
                ).to_dict()
            )
            if len(docs) >= limit:
                return docs
    return docs


# ---------------------------------------------------------------------------
# Public entry point — merge across sources, dedupe by URL
# ---------------------------------------------------------------------------


@cache.cached("reports:kr:v4", ttl=12 * 3600)
def search_reports(company: str, limit: int = 5) -> list[dict[str, Any]]:
    """Aggregate analyst reports for a Korean company across Naver Finance
    Research and Hankyung Consensus. Results are deduped by URL and capped
    at ``limit``. Errors from any one source are reported in-band so the
    caller can see which feed broke."""
    all_docs: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    errors: list[str] = []

    def _ingest(docs: list[dict[str, Any]]) -> None:
        for d in docs:
            url = d.get("url") or ""
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            all_docs.append(d)

    # 1) Naver Finance Research — primary source for most covered tickers.
    try:
        _ingest(_via_naver_research(company, limit))
    except Exception as e:
        errors.append(f"naver_research: {e}")

    # 2) Hankyung Consensus direct — complements Naver, often older reports
    if len(all_docs) < limit:
        try:
            _ingest(_via_hankyung_direct(company, limit - len(all_docs)))
        except Exception as e:
            errors.append(f"hankyung_direct: {e}")

    # 3) Fallback: Naver web search restricted to consensus.hankyung.com
    if len(all_docs) < limit:
        try:
            _ingest(_via_naver_site_filter(company, limit - len(all_docs)))
        except Exception as e:
            errors.append(f"naver_site_filter: {e}")

    if not all_docs:
        return [{"error": " | ".join(errors) or "no analyst reports found"}]
    return all_docs[:limit]
