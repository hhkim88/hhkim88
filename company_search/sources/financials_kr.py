"""Korean financial statements & disclosures via OpenDART."""

from __future__ import annotations

import io
import os
import zipfile
from typing import Any
from xml.etree import ElementTree as ET

import requests

from .. import cache

OPENDART_BASE = "https://opendart.fss.or.kr/api"


def _api_key() -> str:
    key = os.environ.get("DART_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "DART_API_KEY is not set. Get one free at https://opendart.fss.or.kr"
        )
    return key


@cache.cached("dart:corp_codes", ttl=7 * 24 * 3600)
def _corp_code_index() -> dict[str, dict[str, str]]:
    """Download the master XML mapping company name -> corp_code (ZIP-packed)."""
    r = requests.get(
        f"{OPENDART_BASE}/corpCode.xml",
        params={"crtfc_key": _api_key()},
        timeout=30,
    )
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    xml_bytes = z.read(z.namelist()[0])
    root = ET.fromstring(xml_bytes)
    mapping: dict[str, dict[str, str]] = {}
    for item in root.findall("list"):
        name = (item.findtext("corp_name") or "").strip()
        code = (item.findtext("corp_code") or "").strip()
        stock_code = (item.findtext("stock_code") or "").strip()
        if name and code:
            mapping[name] = {"corp_code": code, "stock_code": stock_code}
    return mapping


def find_corp_code(company_name: str) -> str | None:
    idx = _corp_code_index()
    if company_name in idx:
        return idx[company_name]["corp_code"]
    for name, info in idx.items():
        if company_name in name or name in company_name:
            return info["corp_code"]
    return None


@cache.cached("dart:financials", ttl=24 * 3600)
def get_annual_financials(company_name: str, year: int) -> dict[str, Any]:
    """Single-year consolidated annual financials (사업보고서)."""
    corp_code = find_corp_code(company_name)
    if not corp_code:
        return {"company": company_name, "year": year, "error": "corp_code not found"}
    r = requests.get(
        f"{OPENDART_BASE}/fnlttSinglAcntAll.json",
        params={
            "crtfc_key": _api_key(),
            "corp_code": corp_code,
            "bsns_year": str(year),
            "reprt_code": "11011",  # annual report
            "fs_div": "CFS",  # consolidated
        },
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    rows = data.get("list", [])
    summary: dict[str, Any] = {}
    keep_keys = {
        "매출액": "revenue",
        "영업이익": "operating_income",
        "당기순이익": "net_income",
        "자산총계": "total_assets",
        "부채총계": "total_liabilities",
        "자본총계": "total_equity",
    }
    for row in rows:
        nm = row.get("account_nm", "")
        if nm in keep_keys:
            try:
                amt = int((row.get("thstrm_amount") or "0").replace(",", ""))
            except ValueError:
                continue
            summary[keep_keys[nm]] = amt
    return {
        "company": company_name,
        "corp_code": corp_code,
        "year": year,
        "status": data.get("status"),
        "message": data.get("message"),
        "summary_krw": summary,
        "raw_count": len(rows),
    }


@cache.cached("dart:disclosures", ttl=6 * 3600)
def list_recent_disclosures(company_name: str, limit: int = 10) -> list[dict[str, Any]]:
    corp_code = find_corp_code(company_name)
    if not corp_code:
        return []
    r = requests.get(
        f"{OPENDART_BASE}/list.json",
        params={
            "crtfc_key": _api_key(),
            "corp_code": corp_code,
            "page_count": min(limit, 100),
        },
        timeout=30,
    )
    r.raise_for_status()
    items = r.json().get("list", []) or []
    out = []
    for it in items[:limit]:
        rcept_no = it.get("rcept_no", "")
        out.append(
            {
                "title": it.get("report_nm", ""),
                "date": it.get("rcept_dt", ""),
                "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}",
                "rcept_no": rcept_no,
            }
        )
    return out
