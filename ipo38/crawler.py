"""고수준 크롤러: 여러 페이지를 순회하며 정규화된 레코드를 수집한다."""

from __future__ import annotations

import time

import pandas as pd

from . import config, fetch, parse


# 컬럼별 숫자 정규화 함수
_PRICE_FIELDS = ("offer_price", "open_price", "current_price", "close_price", "high_price")
_COMP_FIELDS = ("subscription_competition", "institutional_competition")
_PCT_FIELDS = ("return_pct", "lockup_ratio")


def _normalize_record(rec: dict) -> dict:
    out = dict(rec)
    for f in _PRICE_FIELDS:
        if f in out:
            out[f] = parse.parse_price(out[f])
    for f in _COMP_FIELDS:
        if f in out:
            out[f] = parse.parse_competition(out[f])
    for f in _PCT_FIELDS:
        if f in out:
            out[f] = parse.parse_percent(out[f])
    if "name" in out:
        out["name"] = out["name"].strip()
    return out


def crawl_page_param(
    page_param: str,
    max_pages: int = 20,
    delay: float | None = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """주어진 o= 파라미터 페이지를 max_pages 까지 순회 수집.

    빈 페이지가 나오거나 직전과 동일한 종목 집합이면 중단(마지막 페이지 반복 방지).
    """
    delay = config.REQUEST_DELAY if delay is None else delay
    session = fetch.make_session()
    all_records: list[dict] = []
    seen_signatures: set[frozenset] = set()

    for page in range(1, max_pages + 1):
        html = fetch.fetch_page(page_param, page=page, session=session)
        recs = parse.parse_fund_page(html, page_param)
        if not recs:
            if verbose:
                print(f"  [o={page_param}] page {page}: 데이터 없음 -> 중단")
            break

        names = frozenset(r.get("name", "") for r in recs)
        if names in seen_signatures:
            if verbose:
                print(f"  [o={page_param}] page {page}: 이전 페이지와 동일 -> 중단")
            break
        seen_signatures.add(names)

        all_records.extend(_normalize_record(r) for r in recs)
        if verbose:
            print(f"  [o={page_param}] page {page}: {len(recs)}건 수집")
        time.sleep(delay)

    df = pd.DataFrame(all_records)
    if not df.empty and "name" in df:
        df = df.drop_duplicates(subset=["name"], keep="first").reset_index(drop=True)
    return df


def crawl_subscriptions(max_pages: int = 20, **kw) -> pd.DataFrame:
    """공모주 청약일정 (일반 청약경쟁률 포함)."""
    return crawl_page_param(config.PAGE_SUBSCRIPTION, max_pages=max_pages, **kw)


def crawl_new_listings(max_pages: int = 20, **kw) -> pd.DataFrame:
    """신규상장 종목 (공모가/시초가/현재가 -> 첫날 수익률 계산용)."""
    return crawl_page_param(config.PAGE_NEW_LISTING, max_pages=max_pages, **kw)


def crawl_demand(max_pages: int = 20, **kw) -> pd.DataFrame:
    """수요예측 결과 (기관경쟁률/의무보유확약 등, 선택)."""
    return crawl_page_param(config.PAGE_DEMAND, max_pages=max_pages, **kw)
