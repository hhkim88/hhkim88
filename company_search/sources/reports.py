"""Public analyst reports. Hankyung Consensus (KR) + scraped PDFs."""

from __future__ import annotations

import io
import time
from typing import Any
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

from .. import cache
from ..schema import CompanyDoc

UA = "Mozilla/5.0 (Linux; company-search/0.1)"
HANKYUNG_BASE = "https://consensus.hankyung.com"


def _extract_pdf(url: str) -> str:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        r.raise_for_status()
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(r.content))
        text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
        return text[:12000]
    except Exception:
        return ""


@cache.cached("reports:kr", ttl=12 * 3600)
def search_reports(company: str, limit: int = 5) -> list[dict[str, Any]]:
    """Search Hankyung Consensus for analyst reports mentioning the company."""
    search_url = f"{HANKYUNG_BASE}/search?keyword={quote(company)}"
    try:
        r = requests.get(search_url, headers={"User-Agent": UA}, timeout=15)
        r.raise_for_status()
    except Exception as e:
        return [{"error": f"hankyung fetch failed: {e}"}]
    soup = BeautifulSoup(r.text, "lxml")
    docs: list[dict[str, Any]] = []
    for row in soup.select("table tr")[:limit * 3]:
        cells = row.select("td")
        if len(cells) < 3:
            continue
        link = row.select_one("a[href]")
        if not link:
            continue
        title = link.get_text(strip=True)
        href = urljoin(HANKYUNG_BASE, link["href"])
        # Try to find PDF link in the same row
        pdf_link = None
        for a in row.select("a[href*='.pdf'], a[href*='download']"):
            pdf_link = urljoin(HANKYUNG_BASE, a["href"])
            break
        body = ""
        if pdf_link:
            time.sleep(0.5)
            body = _extract_pdf(pdf_link)
        broker = cells[1].get_text(strip=True) if len(cells) > 1 else ""
        date = cells[-1].get_text(strip=True) if cells else ""
        doc = CompanyDoc(
            company=company,
            ticker=None,
            market="KR",
            source="report",
            url=pdf_link or href,
            title=title,
            body_md=body,
            metadata={"broker": broker, "report_date": date},
        )
        docs.append(doc.to_dict())
        if len(docs) >= limit:
            break
    return docs
