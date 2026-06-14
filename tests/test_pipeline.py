"""오프라인 fixture 로 파서 + 분석 파이프라인을 검증."""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ipo38 import analyze, config, parse  # noqa: E402
from ipo38.crawler import _normalize_record  # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return f.read()


def _df_from_fixture(name, page_param):
    recs = parse.parse_fund_page(_load_fixture(name), page_param)
    return pd.DataFrame(_normalize_record(r) for r in recs)


# --- 숫자 파서 ---
def test_parse_competition():
    assert parse.parse_competition("1,852.30:1") == 1852.30
    assert parse.parse_competition("980.00 : 1") == 980.00
    assert parse.parse_competition("미달") is None
    assert parse.parse_competition("-") is None


def test_parse_price():
    assert parse.parse_price("15,000원") == 15000.0
    assert parse.parse_price("-") is None


# --- 헤더 매핑 (희망공모가 vs 확정공모가 우선순위) ---
def test_header_mapping():
    assert parse.map_header("희망공모가") == "desired_price_band"
    assert parse.map_header("확정공모가") == "offer_price"
    assert parse.map_header("청약경쟁률") == "subscription_competition"
    assert parse.map_header("종목명") == "name"


# --- 테이블 파싱 ---
def test_parse_subscriptions():
    df = _df_from_fixture("subscriptions.html", config.PAGE_SUBSCRIPTION)
    assert len(df) == 4
    assert set(df["name"]) == {"알파바이오", "베타소재", "감마로보틱스", "델타에너지"}
    row = df[df["name"] == "델타에너지"].iloc[0]
    assert row["subscription_competition"] == 55.10
    assert row["offer_price"] == 10000.0


def test_parse_new_listings():
    df = _df_from_fixture("new_listings.html", config.PAGE_NEW_LISTING)
    assert len(df) == 4
    row = df[df["name"] == "알파바이오"].iloc[0]
    assert row["open_price"] == 22500.0
    assert row["close_price"] == 19500.0


# --- 첫날 수익률 계산 ---
def test_first_day_return():
    sub = _df_from_fixture("subscriptions.html", config.PAGE_SUBSCRIPTION)
    ret = _df_from_fixture("new_listings.html", config.PAGE_NEW_LISTING)
    merged = analyze.merge_subscription_returns(sub, ret)
    delta = merged[merged["name"] == "델타에너지"].iloc[0]
    # 공모가 10,000 -> 종가 26,000 = +160%
    assert abs(delta["first_day_return_close"] - 160.0) < 1e-6
    assert abs(delta["first_day_return_open"] - 100.0) < 1e-6
    assert abs(delta["first_day_return"] - 160.0) < 1e-6


# --- 기회 탐색: 낮은 경쟁률 + 높은 수익률 ---
def test_find_opportunities():
    sub = _df_from_fixture("subscriptions.html", config.PAGE_SUBSCRIPTION)
    ret = _df_from_fixture("new_listings.html", config.PAGE_NEW_LISTING)
    merged = analyze.merge_subscription_returns(sub, ret)
    # 델타에너지: 경쟁률 55:1(최저) + 수익률 160%(최고) -> 효율 1위 기대
    opp = analyze.find_opportunities(merged, max_competition=200, min_return=30)
    assert opp.iloc[0]["name"] == "델타에너지"
    # 알파바이오는 경쟁률 1852:1 로 max_competition 200 초과 -> 제외
    assert "알파바이오" not in set(opp["name"])


def test_correlation_report():
    sub = _df_from_fixture("subscriptions.html", config.PAGE_SUBSCRIPTION)
    ret = _df_from_fixture("new_listings.html", config.PAGE_NEW_LISTING)
    merged = analyze.merge_subscription_returns(sub, ret)
    rep = analyze.correlation_report(merged)
    assert rep["n"] == 4
    assert "spearman_comp_vs_return" in rep
