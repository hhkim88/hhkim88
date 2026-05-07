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


@cache.cached("dart:shares:v1", ttl=24 * 3600)
def get_shares_outstanding(company_name: str, year: int) -> dict[str, Any]:
    """Total issued shares from DART stockTotqySttus.json.

    Needed for valuation ratios (PER, PBR, market-cap). Without this,
    moderator-side recommendations have to guess share counts and end up
    with wildly wrong PER. We fetch and split by class so callers can
    decide whether to use common-only or total.
    """
    corp_code = find_corp_code(company_name)
    if not corp_code:
        return {"company": company_name, "year": year, "error": "corp_code not found"}
    r = requests.get(
        f"{OPENDART_BASE}/stockTotqySttus.json",
        params={
            "crtfc_key": _api_key(),
            "corp_code": corp_code,
            "bsns_year": str(year),
            "reprt_code": "11011",  # annual report
        },
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    rows = data.get("list", []) or []

    common_shares = 0
    preferred_shares = 0
    by_class: list[dict[str, Any]] = []
    for row in rows:
        se = (row.get("se") or "").strip()
        # DART exposes the issued total under different keys depending on
        # report version; cover both common variants.
        raw = row.get("istc_totqy") or row.get("isu_stock_totqy") or "0"
        try:
            count = int(str(raw).replace(",", "").strip() or "0")
        except ValueError:
            count = 0
        if not count:
            continue
        by_class.append({"class": se, "issued": count})
        if "보통주" in se:
            common_shares = max(common_shares, count)
        elif "우선" in se:
            preferred_shares = max(preferred_shares, count)

    # Fallback: if nothing matched 보통주/우선, take the largest single-row count
    total_shares = common_shares + preferred_shares
    if total_shares == 0 and by_class:
        total_shares = max(c["issued"] for c in by_class)
        if common_shares == 0:
            common_shares = total_shares

    return {
        "company": company_name,
        "corp_code": corp_code,
        "year": year,
        "status": data.get("status"),
        "message": data.get("message"),
        "common_shares": common_shares,
        "preferred_shares": preferred_shares,
        "total_shares": total_shares,
        "by_class": by_class,
    }


@cache.cached("dart:financials:v3", ttl=24 * 3600)
def get_annual_financials(company_name: str, year: int) -> dict[str, Any]:
    """Single-year consolidated annual financials (사업보고서) plus shares
    outstanding so the caller can compute PER / PBR / market-cap directly."""
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
    # DART repeats the same account_nm across statement types (BS/IS/CIS/CF/SCE),
    # often with very different signs and magnitudes. Without filtering we'd
    # overwrite balance-sheet totals with statement-of-changes-in-equity rows
    # (which can be negative for net movement). Pin each field to its expected
    # statement type and prefer the first non-zero match.
    expected_sj_div = {
        "revenue": "IS",
        "operating_income": "IS",
        "net_income": "IS",
        "total_assets": "BS",
        "total_liabilities": "BS",
        "total_equity": "BS",
    }
    for row in rows:
        nm = row.get("account_nm", "")
        if nm not in keep_keys:
            continue
        target = keep_keys[nm]
        sj_div = (row.get("sj_div") or "").strip()
        # If DART supplies sj_div, require the canonical statement type.
        if sj_div and sj_div != expected_sj_div[target]:
            continue
        try:
            amt = int((row.get("thstrm_amount") or "0").replace(",", ""))
        except ValueError:
            continue
        # Prefer the first non-zero hit; don't let later rows overwrite a good
        # value with 0 or a different statement's number.
        if summary.get(target):
            continue
        summary[target] = amt

    # Best-effort: pull shares outstanding from the dedicated DART endpoint.
    # Failure here must not break the financials call.
    shares_block: dict[str, Any] = {}
    try:
        shares = get_shares_outstanding(company_name, year)
        if isinstance(shares, dict) and shares.get("total_shares"):
            shares_block = {
                "common_shares": shares.get("common_shares") or 0,
                "preferred_shares": shares.get("preferred_shares") or 0,
                "total_shares": shares.get("total_shares") or 0,
            }
    except Exception as exc:
        shares_block = {"shares_error": str(exc)[:200]}

    # Quick derived metrics so the moderator doesn't have to estimate.
    derived: dict[str, Any] = {}
    common = shares_block.get("common_shares") or 0
    if common and summary.get("net_income"):
        derived["eps_krw"] = summary["net_income"] / common
    if common and summary.get("total_equity"):
        derived["bps_krw"] = summary["total_equity"] / common

    return {
        "company": company_name,
        "corp_code": corp_code,
        "year": year,
        "status": data.get("status"),
        "message": data.get("message"),
        "summary_krw": summary,
        "shares_outstanding": shares_block,
        "per_share_krw": derived,
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
