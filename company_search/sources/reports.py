"""Public Korean analyst reports — Hankyung Consensus.

Hankyung's site has been migrated repeatedly so the previous single
hard-coded URL frequently 404'd. We try several known URL patterns and
parse them with multiple selectors. If the site itself is unreachable we
fall back to a Naver web search restricted to ``site:consensus.hankyung.com``,
which surfaces the same documents through a different door.
"""

from __future__ import annotations

import io
from typing import Any
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

from .. import cache
from .._http import browser_headers, get_html
from ..schema import CompanyDoc

HANKYUNG_BASE = "https://consensus.hankyung.com"
_LIST_URLS = (
    HANKYUNG_BASE + "/analysis/list?keyword={q}",
    HANKYUNG_BASE + "/search?keyword={q}",
    HANKYUNG_BASE + "/apps.analysis/analysis.list?search_text={q}",
)


def _extract_pdf(url: str) -> str:
    """Download a PDF and pull its text. Empty string on any failure."""
    try:
        r = requests.get(
            url,
            headers=browser_headers(referer=HANKYUNG_BASE + "/"),
            timeout=30,
        )
        r.raise_for_status()
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(r.content))
        text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
        return text[:12000]
    except Exception:
        return ""


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
                metadata={"broker": broker, "report_date": date},
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
                    metadata={"broker": "", "report_date": ""},
                ).to_dict()
            )
            if len(docs) >= limit:
                return docs
    return docs


@cache.cached("reports:kr", ttl=12 * 3600)
def search_reports(company: str, limit: int = 5) -> list[dict[str, Any]]:
    errors: list[str] = []

    try:
        docs = _via_hankyung_direct(company, limit)
        if docs:
            return docs
    except Exception as e:
        errors.append(f"hankyung_direct: {e}")

    try:
        docs = _via_naver_site_filter(company, limit)
        if docs:
            return docs
    except Exception as e:
        errors.append(f"naver_site_filter: {e}")

    return [{"error": " | ".join(errors) or "no Hankyung Consensus reports found"}]
