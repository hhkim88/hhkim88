"""분석: '청약경쟁률은 낮고(당첨 확률 높음) + 첫날 수익률은 높은' 조건 탐색.

핵심 아이디어
------------
- 일반 개인투자자 청약경쟁률(subscription_competition)이 낮을수록 비례배정에서
  같은 청약증거금으로 더 많은 주식을 배정받을 확률이 높다(=당첨 확률 ↑).
- 첫날 수익률(first_day_return_close 또는 _open)이 높을수록 상장 직후 수익이 크다.
- 두 조건을 함께 만족하는 종목이 '효율 좋은' 공모주다.

배정 효율 지표
-------------
비례배정 배정주수는 대략 (청약주수 / 경쟁률) 에 비례하므로,
1주당 기대수익 효율을 근사하는 점수로 다음을 쓴다.

    efficiency = first_day_return(%) / sqrt(subscription_competition)

경쟁률이 낮을수록, 수익률이 높을수록 점수가 커진다.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _norm_name(s: str) -> str:
    """병합용 종목명 정규화: 공백/괄호 내용 제거."""
    if not isinstance(s, str):
        return ""
    s = s.split("(")[0]
    return "".join(s.split())


def compute_first_day_return(df: pd.DataFrame) -> pd.DataFrame:
    """공모가 대비 첫날 수익률(%) 컬럼을 계산해 추가.

    - first_day_return_open : (시초가 - 공모가) / 공모가 * 100
    - first_day_return_close: (당일 종가 - 공모가) / 공모가 * 100
    - first_day_return       : close 우선, 없으면 open, 없으면 사이트 제공 return_pct
    """
    out = df.copy()

    def pct(numer_col):
        if numer_col in out and "offer_price" in out:
            return (out[numer_col] - out["offer_price"]) / out["offer_price"] * 100.0
        return pd.Series([np.nan] * len(out), index=out.index)

    out["first_day_return_open"] = pct("open_price")
    out["first_day_return_close"] = pct("close_price")

    fallback = out["return_pct"] if "return_pct" in out else np.nan
    out["first_day_return"] = (
        out["first_day_return_close"]
        .fillna(out["first_day_return_open"])
        .fillna(fallback)
    )
    return out


def merge_subscription_returns(
    df_sub: pd.DataFrame, df_ret: pd.DataFrame
) -> pd.DataFrame:
    """청약(경쟁률) 데이터와 신규상장(수익률) 데이터를 종목명으로 병합."""
    a = df_sub.copy()
    b = df_ret.copy()
    a["_key"] = a["name"].map(_norm_name)
    b["_key"] = b["name"].map(_norm_name)

    # 양쪽 중복 컬럼은 신규상장(b) 값을 우선 사용 (가격/수익률 신선도)
    overlap = [c for c in b.columns if c in a.columns and c not in ("_key", "name")]
    a = a.drop(columns=overlap, errors="ignore")

    merged = a.merge(b.drop(columns=["name"]), on="_key", how="inner")
    merged = merged.drop(columns=["_key"])
    return compute_first_day_return(merged)


def add_efficiency_score(df: pd.DataFrame) -> pd.DataFrame:
    """배정 효율 점수 추가."""
    out = df.copy()
    comp = out.get("subscription_competition")
    ret = out.get("first_day_return")
    if comp is None or ret is None:
        out["efficiency"] = np.nan
        return out
    safe_comp = comp.where(comp > 0)
    out["efficiency"] = ret / np.sqrt(safe_comp)
    return out


def find_opportunities(
    df: pd.DataFrame,
    max_competition: float | None = None,
    min_return: float = 0.0,
    competition_quantile: float = 0.5,
    return_quantile: float = 0.5,
) -> pd.DataFrame:
    """'낮은 청약경쟁률 + 높은 첫날 수익률' 종목 필터링.

    max_competition 을 직접 주면 그 값 이하로 필터.
    주지 않으면 competition_quantile(하위 분위) 이하 경쟁률 +
    return_quantile(상위 분위) 이상 수익률 조건을 동시에 적용.
    """
    work = add_efficiency_score(df).dropna(
        subset=["subscription_competition", "first_day_return"]
    )
    if work.empty:
        return work

    if max_competition is not None:
        comp_mask = work["subscription_competition"] <= max_competition
    else:
        comp_cut = work["subscription_competition"].quantile(competition_quantile)
        comp_mask = work["subscription_competition"] <= comp_cut

    ret_cut = max(min_return, work["first_day_return"].quantile(return_quantile))
    ret_mask = work["first_day_return"] >= ret_cut

    result = work[comp_mask & ret_mask].copy()
    return result.sort_values("efficiency", ascending=False).reset_index(drop=True)


def correlation_report(df: pd.DataFrame) -> dict:
    """청약경쟁률과 첫날 수익률의 상관관계 등 요약 통계."""
    work = add_efficiency_score(df).dropna(
        subset=["subscription_competition", "first_day_return"]
    )
    rep: dict = {"n": int(len(work))}
    if len(work) >= 3:
        rep["pearson_comp_vs_return"] = float(
            work["subscription_competition"].corr(work["first_day_return"])
        )
        # Spearman = 순위로 변환한 뒤 Pearson (scipy 의존성 회피)
        rep["spearman_comp_vs_return"] = float(
            work["subscription_competition"].rank().corr(
                work["first_day_return"].rank()
            )
        )
        rep["mean_return"] = float(work["first_day_return"].mean())
        rep["median_return"] = float(work["first_day_return"].median())
        rep["mean_competition"] = float(work["subscription_competition"].mean())
        rep["median_competition"] = float(work["subscription_competition"].median())
    return rep


def summarize(rep: dict) -> str:
    if rep.get("n", 0) < 3:
        return f"분석 가능한 종목 수가 부족합니다 (n={rep.get('n', 0)})."
    sp = rep["spearman_comp_vs_return"]
    if sp < -0.1:
        rel = "경쟁률이 낮을수록 수익률이 높은 경향(역상관) → 가설을 지지합니다."
    elif sp > 0.1:
        rel = "경쟁률이 높을수록 수익률도 높은 경향(정상관) → 가설과 반대입니다."
    else:
        rel = "경쟁률과 수익률 간 뚜렷한 상관관계가 보이지 않습니다."
    return (
        f"분석 종목 수: {rep['n']}\n"
        f"평균/중앙값 첫날 수익률: {rep['mean_return']:.1f}% / {rep['median_return']:.1f}%\n"
        f"평균/중앙값 청약경쟁률: {rep['mean_competition']:.1f}:1 / {rep['median_competition']:.1f}:1\n"
        f"경쟁률 vs 수익률 상관계수 (Spearman): {sp:.3f}\n"
        f"해석: {rel}"
    )
