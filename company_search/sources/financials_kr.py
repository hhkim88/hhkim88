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


def _stock_code_to_corp(idx: dict[str, dict[str, str]]) -> dict[str, str]:
    return {
        info["stock_code"]: info["corp_code"]
        for info in idx.values()
        if info.get("stock_code")
    }


def find_corp_code(company_name: str) -> str | None:
    idx = _corp_code_index()

    # 1. Exact match on DART's official corp_name.
    if company_name in idx:
        return idx[company_name]["corp_code"]

    # 2. Resolve via the 6-digit KRX stock code. DART's official name often
    #    differs from the common/FDR short name ("현대자동차" vs "현대차"), and a
    #    naive substring match then either misses entirely (현대차 is NOT a
    #    substring of 현대자동차) or latches onto an unrelated listed entity
    #    (현대차증권) or an unlisted subsidiary with no 사업보고서 → DART
    #    status 013. Matching on the stock code is unambiguous.
    q = company_name.strip()
    stock_code = q if (q.isdigit() and len(q) == 6) else None
    if stock_code is None:
        try:
            from .. import ticker as _ticker

            info = _ticker.resolve(q, market="KR")
            if info and info.ticker.isdigit() and len(info.ticker) == 6:
                stock_code = info.ticker
        except Exception:
            stock_code = None
    if stock_code:
        corp = _stock_code_to_corp(idx).get(stock_code)
        if corp:
            return corp

    # 3. Substring fallback, preferring listed companies (stock_code set) so a
    #    query doesn't resolve to an unlisted subsidiary that files no reports.
    unlisted_match: str | None = None
    for name, sub_info in idx.items():
        if q in name or name in q:
            if sub_info.get("stock_code"):
                return sub_info["corp_code"]
            if unlisted_match is None:
                unlisted_match = sub_info["corp_code"]
    return unlisted_match


@cache.cached("dart:shares:v2", ttl=24 * 3600)
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


def _fetch_dart_financials(corp_code: str, year: int, fs_div: str) -> dict[str, Any]:
    r = requests.get(
        f"{OPENDART_BASE}/fnlttSinglAcntAll.json",
        params={
            "crtfc_key": _api_key(),
            "corp_code": corp_code,
            "bsns_year": str(year),
            "reprt_code": "11011",  # annual report
            "fs_div": fs_div,
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


# Map DART account_nm variants to our canonical fields. Different filers use
# slightly different names (e.g. financial holdings file "수익(매출액)" instead
# of "매출액"; some firms tag operating income with "(손실)" suffix).
_ACCOUNT_NM_MAP: dict[str, str] = {
    "매출액": "revenue",
    "수익(매출액)": "revenue",
    "영업수익": "revenue",
    "매출": "revenue",
    "영업이익": "operating_income",
    "영업이익(손실)": "operating_income",
    "영업손실": "operating_income",
    "당기순이익": "net_income",
    "당기순이익(손실)": "net_income",
    "당기순손실": "net_income",
    "자산총계": "total_assets",
    "부채총계": "total_liabilities",
    "자본총계": "total_equity",
}

# DART splits each filing into sj_div sections. Income items live in IS for
# K-GAAP filers and CIS (포괄손익계산서) for IFRS filers — both must be
# accepted, otherwise IFRS filers (most KOSPI/KOSDAQ listings) silently lose
# all revenue / operating income / net income.
_EXPECTED_SJ_DIV: dict[str, tuple[str, ...]] = {
    "revenue": ("IS", "CIS"),
    "operating_income": ("IS", "CIS"),
    "net_income": ("IS", "CIS"),
    "total_assets": ("BS",),
    "total_liabilities": ("BS",),
    "total_equity": ("BS",),
}


# K-IFRS consolidated filings include split rows that contain the canonical
# name as a substring (e.g. "지배기업 소유주지분 당기순이익", "비지배지분
# 당기순이익", "기본주당이익"). The substring fallback in _extract_summary must
# skip these or it will overwrite the consolidated total with one of the
# components. 현대자동차 surfaces "당기순이익" with annotations that break exact
# matching but contains the canonical substring; without rejection the loop
# picks the 지배기업-share row first and net_income stays uncomputable.
_SPLIT_LINE_TOKENS: tuple[str, ...] = ("지배", "비지배", "주당")

_TARGETS: tuple[str, ...] = (
    "revenue",
    "operating_income",
    "net_income",
    "total_assets",
    "total_liabilities",
    "total_equity",
)


def _parse_amount(s: Any) -> int | None:
    try:
        return int(str(s if s is not None else "0").replace(",", "").strip() or "0")
    except (ValueError, TypeError):
        return None


# DART annual filings carry three fiscal years per row (당기/전기/전전기).
# Extracting all three from one call gives real multi-year CAGR/OPM trends
# for the moderator's C-0 종목 분류 without any extra API requests.
_AMOUNT_COLS: dict[str, str] = {
    "y0": "thstrm_amount",     # 당기 (current fiscal year)
    "y1": "frmtrm_amount",     # 전기 (prior year)
    "y2": "bfefrmtrm_amount",  # 전전기 (two years prior)
}


def _match_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Two-pass mapping of DART rows → canonical fields.

    Pass 1 (exact name match) handles the common case. Pass 2 falls back to
    substring matching for fields still missing, after rejecting split-line
    variants — needed for K-IFRS filers (e.g. 현대자동차) whose account_nm
    carries extra annotation that breaks exact equality. A row only matches
    if its 당기 amount parses, mirroring the original summary behavior.
    """
    matched: dict[str, dict[str, Any]] = {}

    for row in rows:
        nm = (row.get("account_nm") or "").strip()
        target = _ACCOUNT_NM_MAP.get(nm)
        if not target or target in matched:
            continue
        sj_div = (row.get("sj_div") or "").strip()
        if sj_div and sj_div not in _EXPECTED_SJ_DIV[target]:
            continue
        if _parse_amount(row.get("thstrm_amount")) is None:
            continue
        matched[target] = row

    missing = [f for f in _TARGETS if f not in matched]
    if not missing:
        return matched

    for row in rows:
        nm = (row.get("account_nm") or "").strip()
        if any(tok in nm for tok in _SPLIT_LINE_TOKENS):
            continue
        sj_div = (row.get("sj_div") or "").strip()
        for canonical, field in _ACCOUNT_NM_MAP.items():
            if field not in missing:
                continue
            if canonical not in nm:
                continue
            if sj_div and sj_div not in _EXPECTED_SJ_DIV[field]:
                continue
            if _parse_amount(row.get("thstrm_amount")) is None:
                continue
            matched[field] = row
            missing.remove(field)
            break

    return matched


def _extract_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Current-year (당기) view — backward compatible with prior callers."""
    out: dict[str, int] = {}
    for field, row in _match_rows(rows).items():
        amt = _parse_amount(row.get("thstrm_amount"))
        if amt is not None:
            out[field] = amt
    return out


def _extract_multi_year(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """3-year series {field: {y0, y1, y2}} from a single filing.

    Zero amounts are skipped — in DART data a 0 in 전기/전전기 columns means
    "not reported", not an actual zero.
    """
    out: dict[str, dict[str, int]] = {}
    for field, row in _match_rows(rows).items():
        years: dict[str, int] = {}
        for label, col in _AMOUNT_COLS.items():
            amt = _parse_amount(row.get(col))
            if amt:
                years[label] = amt
        if years:
            out[field] = years
    return out


# Curated whitelist of KR cyclical large-caps. CAGR/OPM signals alone misread
# cyclical upcycles as hypergrowth (SK하이닉스 2023→2025: CAGR +72%, OPM
# +7219bps → suggested_class "C 하이퍼그로스" without this guard). Code → label.
# Kept conservative: only sectors with documented EPS YoY ±50% history.
_CYCLICAL_KR_CODES: dict[str, str] = {
    # 메모리·반도체·반도체장비
    "000660": "메모리 (SK하이닉스)",
    "005930": "반도체·전자 (삼성전자)",
    "042700": "반도체 장비 (한미반도체)",
    "240810": "반도체 장비 (원익IPS)",
    "036930": "반도체 장비 (주성엔지니어링)",
    "357780": "반도체 소재 (솔브레인)",
    "058470": "반도체 부품 (리노공업)",
    "095340": "반도체 후공정 (ISC)",
    "131970": "반도체 패키징 (두산테스나)",
    "121600": "반도체·디스플레이 소재 (나노신소재)",
    "005070": "반도체·2차전지 소재 (코스모신소재)",
    # 자동차·자동차부품
    "005380": "자동차 (현대차)",
    "000270": "자동차 (기아)",
    "012330": "자동차 부품 (현대모비스)",
    "011210": "자동차 부품 (현대위아)",
    "161390": "타이어 (한국타이어앤테크놀로지)",
    "005720": "타이어 (넥센)",
    # 철강·금속·비철
    "005490": "철강 (POSCO홀딩스)",
    "004020": "철강 (현대제철)",
    "010130": "비철금속 (고려아연)",
    "005010": "강관 (휴스틸)",
    "002240": "특수강 (고려제강)",
    "010520": "철강 (현대비앤지스틸)",
    # 조선·해운
    "010140": "조선 (삼성중공업)",
    "009540": "조선 (HD한국조선해양)",
    "042660": "조선 (한화오션)",
    "010620": "조선 (현대미포조선)",
    "092200": "조선기자재 (HSD엔진)",
    "011200": "해운 (HMM)",
    "044450": "해운 (KSS해운)",
    # 화학·정유·소재
    "051910": "화학 (LG화학)",
    "011170": "화학 (롯데케미칼)",
    "009830": "화학 (한화솔루션)",
    "010060": "화학 (OCI홀딩스)",
    "298050": "소재 (효성첨단소재)",
    "011780": "석유화학 (금호석유)",
    "096770": "정유 (SK이노베이션)",
    "010950": "정유 (S-Oil)",
    "003670": "2차전지 소재 (포스코퓨처엠)",
    # 건설기계·산업기계
    "042670": "건설기계 (HD현대인프라코어)",
    "241560": "건설기계 (두산밥캣)",
    "267260": "산업기기 (HD현대일렉트릭)",
    "034020": "발전기자재 (두산에너빌리티)",
    "000150": "산업기계 (두산)",
    # 건설
    "000720": "건설 (현대건설)",
    "028260": "건설 (삼성물산)",
    "047040": "건설 (대우건설)",
    "006360": "건설 (GS건설)",
    "375500": "건설 (DL이앤씨)",
    # 시멘트·건자재
    "003410": "시멘트 (쌍용씨앤이)",
    "300720": "시멘트 (한일시멘트)",
    # 디스플레이·전자부품
    "034220": "디스플레이 (LG디스플레이)",
    "011070": "전자부품 (LG이노텍)",
}

# KR industry-name keyword fallback. Matched against FDR `Industry` column
# when stock code isn't whitelisted. Korean industry names follow KSIC.
_CYCLICAL_INDUSTRY_KR_KEYWORDS: dict[str, tuple[str, ...]] = {
    "반도체": ("반도체",),
    "철강·금속": ("1차 철강", "철강", "비철금속", "금속 광업", "광산", "광물"),
    "조선·해운": ("선박", "조선", "해상 운송", "해운", "수상"),
    "화학·정유": ("석유 정제", "기초 화학", "기타 화학", "합성", "고무", "플라스틱", "비료"),
    "건설기계·산업기계": ("건설용 기계", "특수 목적용 기계", "일반 목적용 기계", "엔진"),
    "건설": ("종합 건설", "토목 건설", "건축 건설"),
    "시멘트·건자재": ("시멘트", "비금속 광물"),
    "자동차": ("자동차"),
}


def _match_cyclical_kr(stock_code: str | None, company_name: str | None) -> str | None:
    """Return cyclical bucket label if KR stock matches; None otherwise.

    Whitelist beats keyword match. Keyword match queries FDR's KRX listing
    industry column lazily — failures (no network, missing column) silently
    return None so non-cyclical stocks still flow through the CAGR/OPM path.
    """
    if stock_code and stock_code in _CYCLICAL_KR_CODES:
        return _CYCLICAL_KR_CODES[stock_code]
    try:
        from .. import ticker as _ticker

        df = _ticker._safe_listing(_ticker._kr_listing)
        if df.empty:
            return None
        # FDR uses "Industry" or "industry" — handle both.
        industry_col = next(
            (c for c in df.columns if c.lower() == "industry"), None
        )
        if not industry_col:
            return None
        if stock_code and "Code" in df.columns:
            row = df[df["Code"].astype(str) == stock_code]
        elif company_name and "Name" in df.columns:
            row = df[df["Name"] == company_name]
        else:
            return None
        if row.empty:
            return None
        industry = str(row.iloc[0].get(industry_col) or "").strip()
        if not industry:
            return None
        for label, keywords in _CYCLICAL_INDUSTRY_KR_KEYWORDS.items():
            for kw in keywords:
                if kw in industry:
                    return f"{label} (FDR industry: {industry})"
    except Exception:
        return None
    return None


def _classification_signals_kr(
    multi_year: dict[str, dict[str, int]],
    stock_code: str | None = None,
    company_name: str | None = None,
) -> dict[str, Any]:
    """Growth/margin trend signals for the moderator's C-0 종목 분류.

    suggested_class precedence:
      1. KR cyclical override — whitelist by stock code, FDR-industry keyword
         fallback. Beats any CAGR/OPM signal. SK하이닉스 in a memory upcycle
         looks like C 하이퍼그로스 on numbers alone; this guard forces D
         before the matrix can mis-classify.
      2. CAGR/OPM heuristic on DART's 3-year columns.
    """
    signals: dict[str, Any] = {}
    rev = multi_year.get("revenue", {})
    oi = multi_year.get("operating_income", {})

    if rev.get("y0") and rev.get("y2") and rev["y2"] > 0:
        signals["revenue_cagr_2y"] = round((rev["y0"] / rev["y2"]) ** 0.5 - 1, 4)

    if all(rev.get(y) and oi.get(y) for y in ("y0", "y2")):
        opm0 = oi["y0"] / rev["y0"]
        opm2 = oi["y2"] / rev["y2"]
        signals["opm_y0"] = round(opm0, 4)
        signals["opm_y2"] = round(opm2, 4)
        signals["opm_trend_bps"] = round((opm0 - opm2) * 10000)

    # Step 1: cyclical industry override (beats CAGR/OPM heuristic).
    matched = _match_cyclical_kr(stock_code, company_name)
    if matched:
        signals["industry_raw"] = matched
        signals["suggested_class"] = f"D 사이클 (산업 강제: {matched})"
        return signals

    # Step 2: CAGR/OPM heuristic for non-cyclical industries.
    rev_cagr = signals.get("revenue_cagr_2y")
    opm_trend = signals.get("opm_trend_bps") or 0
    if rev_cagr is not None:
        if rev_cagr < 0:
            signals["suggested_class"] = "E 턴어라운드 검토 (매출 역성장)"
        elif rev_cagr > 0.20 and opm_trend >= 500:
            signals["suggested_class"] = "C 하이퍼그로스"
        elif rev_cagr > 0.20:
            signals["suggested_class"] = "B~C (매출 고성장 — 백로그·OPM 추이로 최종 판단)"
        elif 0.08 <= rev_cagr <= 0.20 and opm_trend > 0:
            signals["suggested_class"] = "B 컴파운더"
        else:
            signals["suggested_class"] = "A 가치/배당"

    return signals


def _resolve_stock_code(company_name: str) -> str | None:
    """Best-effort 6-digit KRX code lookup. Mirrors what find_corp_code does
    internally, but returns the stock code itself so _classification_signals_kr
    can hit the cyclical whitelist directly."""
    q = (company_name or "").strip()
    if q.isdigit() and len(q) == 6:
        return q
    try:
        from .. import ticker as _ticker

        info = _ticker.resolve(q, market="KR")
        if info and info.ticker.isdigit() and len(info.ticker) == 6:
            return info.ticker
    except Exception:
        return None
    return None


@cache.cached("dart:financials:v8", ttl=24 * 3600)
def get_annual_financials(company_name: str, year: int) -> dict[str, Any]:
    """Single-year annual financials (사업보고서) plus shares outstanding.

    Tries consolidated (CFS) first; falls back to standalone (OFS) for
    filers without subsidiaries. Income items accept both IS and CIS so
    K-IFRS filings are not silently dropped.
    """
    corp_code = find_corp_code(company_name)
    if not corp_code:
        return {"company": company_name, "year": year, "error": "corp_code not found"}

    data = _fetch_dart_financials(corp_code, year, "CFS")
    rows = data.get("list", []) or []
    fs_div_used = "CFS"
    if not rows:
        data = _fetch_dart_financials(corp_code, year, "OFS")
        rows = data.get("list", []) or []
        fs_div_used = "OFS"

    # DART signals problems through status codes: "000" success, "013" no data,
    # "100" invalid key, etc. Anything other than success or genuine no-data
    # is a transient/config error — surface it as an error dict so the cache
    # layer treats it as a failure and retries on the next call instead of
    # pinning the bad response for 24h.
    status = data.get("status")
    if status not in ("000", "013"):
        return {
            "error": f"DART status={status}: {data.get('message', '')}",
            "company": company_name,
        }

    summary = _extract_summary(rows)
    multi_year = _extract_multi_year(rows)

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
        "fs_div": fs_div_used,
        "status": data.get("status"),
        "message": data.get("message"),
        "summary_krw": summary,
        # 3개년(당기/전기/전전기) 시계열 + C-0 종목 분류 신호. 추가 API
        # 호출 없이 동일 응답에서 추출되므로 비용 증가 없음.
        "multi_year_krw": multi_year,
        "classification_signals": _classification_signals_kr(
            multi_year,
            stock_code=_resolve_stock_code(company_name),
            company_name=company_name,
        ),
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
