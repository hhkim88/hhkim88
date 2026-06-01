"""US fundamentals via yfinance."""

from __future__ import annotations

from typing import Any

from .. import cache

# Hardcoded long-term US Treasury yield used as the risk-free benchmark for
# FCF-yield sanity checks. We don't pull this dynamically yet — it moves
# slowly enough that a manually bumped constant beats adding a network call
# that can fail and silently zero the spread. Update when the 10y trends
# meaningfully (>50bps).
RISK_FREE_RATE_10Y: float = 0.043  # 4.3%, US 10y Treasury


def _safe_div(num: Any, den: Any) -> float | None:
    try:
        n = float(num)
        d = float(den)
    except (TypeError, ValueError):
        return None
    if not d or d != d or n != n:
        return None
    return n / d


def _valuation_signals(info: dict[str, Any]) -> dict[str, Any]:
    """Derive absolute-valuation sanity signals from yfinance info.

    Surfaces what the moderator's "절대 밸류 새너티 체크" row needs without
    each agent recomputing it: FCF yield vs the risk-free rate, EV/EBITDA,
    and tangible-book ratio. PEG and 가격 위치 percentile rows capture
    relative/historical valuation; this block captures the absolute floor.
    """
    market_cap = info.get("marketCap")
    fcf = info.get("freeCashflow")
    total_debt = info.get("totalDebt") or 0
    total_cash = info.get("totalCash") or 0
    ebitda = info.get("ebitda")

    fcf_yield = _safe_div(fcf, market_cap)
    ev = None
    if market_cap is not None:
        try:
            ev = float(market_cap) + float(total_debt) - float(total_cash)
        except (TypeError, ValueError):
            ev = None
    ev_ebitda = _safe_div(ev, ebitda)

    signals: dict[str, Any] = {
        "risk_free_rate_10y": RISK_FREE_RATE_10Y,
        "fcf_yield": fcf_yield,
        "fcf_yield_minus_rf": (fcf_yield - RISK_FREE_RATE_10Y) if fcf_yield is not None else None,
        "ev_ebitda": ev_ebitda,
        "enterprise_value": ev,
    }
    # Tangible book ratio when info exposes it (yfinance sometimes lacks it
    # for intangible-heavy names — V/ETN — leave None and let the moderator
    # cross-reference the balance sheet block instead).
    p_b = info.get("priceToBook")
    if p_b is not None:
        signals["price_to_book"] = p_b
    return signals


def _classification_signals(
    info: dict[str, Any], statements: dict[str, Any]
) -> dict[str, Any]:
    """Multi-year growth/margin signals for the moderator's C-0 종목 분류.

    Computed from realized annual statements (yfinance, newest column first)
    — never forward estimates, because the matrix variant a stock gets
    (가치/컴파운더/하이퍼그로스) must not be inflatable by consensus hopes.
    `suggested_class` is a hint only; the moderator makes the final call
    (e.g. cyclical industries are classified by sector knowledge, not CAGR).
    """
    signals: dict[str, Any] = {}

    income_rows = (statements.get("income") or {}).get("rows", {})
    cf_rows = (statements.get("cashflow") or {}).get("rows", {})

    def _series(rows: dict[str, Any], *keys: str) -> list[float]:
        for k in keys:
            vals = rows.get(k)
            if vals:
                clean = [v for v in vals if v is not None and v == v]
                if len(clean) >= 2:
                    return clean  # newest first
        return []

    revenue = _series(income_rows, "Total Revenue", "Operating Revenue")
    op_inc = _series(income_rows, "Operating Income", "Total Operating Income As Reported")
    fcf = _series(cf_rows, "Free Cash Flow")

    # Revenue CAGR over the available span (typically 3-4 fiscal years)
    if len(revenue) >= 3 and revenue[-1] > 0:
        years = len(revenue) - 1
        signals["revenue_cagr"] = round((revenue[0] / revenue[-1]) ** (1 / years) - 1, 4)
        signals["revenue_years_spanned"] = years + 1

    # OPM trend in bps: newest fiscal year vs oldest available
    if len(revenue) >= 3 and len(op_inc) >= 3:
        n = min(len(revenue), len(op_inc))
        if revenue[0] and revenue[n - 1]:
            opm_new = op_inc[0] / revenue[0]
            opm_old = op_inc[n - 1] / revenue[n - 1]
            signals["opm_newest"] = round(opm_new, 4)
            signals["opm_oldest"] = round(opm_old, 4)
            signals["opm_trend_bps"] = round((opm_new - opm_old) * 10000)

    # FCF CAGR — only when both endpoints positive (sign flips break CAGR);
    # a negative→positive flip is itself a hypergrowth marker.
    if len(fcf) >= 3:
        if fcf[-1] > 0 and fcf[0] > 0:
            years = len(fcf) - 1
            signals["fcf_cagr"] = round((fcf[0] / fcf[-1]) ** (1 / years) - 1, 4)
        elif fcf[-1] <= 0 < fcf[0]:
            signals["fcf_turned_positive"] = True

    if info.get("dividendYield") is not None:
        signals["dividend_yield"] = info.get("dividendYield")

    # Heuristic hint mirroring the moderator's C-0 table (D/E need industry
    # context the code can't see, so the hint never suggests D).
    rev_cagr = signals.get("revenue_cagr")
    opm_trend = signals.get("opm_trend_bps") or 0
    fcf_cagr = signals.get("fcf_cagr") or 0
    if rev_cagr is not None:
        if rev_cagr < 0:
            signals["suggested_class"] = "E 턴어라운드 검토 (매출 역성장)"
        elif rev_cagr > 0.20 and (signals.get("fcf_turned_positive") or opm_trend >= 500):
            signals["suggested_class"] = "C 하이퍼그로스"
        elif 0.08 <= rev_cagr <= 0.20 and (opm_trend > 0 or fcf_cagr > 0.15):
            signals["suggested_class"] = "B 컴파운더"
        else:
            signals["suggested_class"] = "A 가치/배당"

    return signals


@cache.cached("yf:fundamentals:v3", ttl=24 * 3600)
def get_fundamentals(ticker: str) -> dict[str, Any]:
    import yfinance as yf

    t = yf.Ticker(ticker)
    info: dict[str, Any] = {}
    try:
        raw = t.info or {}
        keep = [
            "longName",
            "sector",
            "industry",
            "marketCap",
            "trailingPE",
            "forwardPE",
            "priceToBook",
            "dividendYield",
            "trailingEps",
            "forwardEps",
            "profitMargins",
            "operatingMargins",
            "returnOnEquity",
            "returnOnAssets",
            "totalRevenue",
            "totalDebt",
            "totalCash",
            "freeCashflow",
            "ebitda",
            "enterpriseValue",
            "enterpriseToEbitda",
            "recommendationKey",
            "targetMeanPrice",
            "currentPrice",
        ]
        info = {k: raw.get(k) for k in keep if k in raw}
    except Exception as e:
        info = {"error": str(e)}

    valuation_signals = _valuation_signals(info) if "error" not in info else {}

    statements: dict[str, Any] = {}
    for attr, label in (
        ("income_stmt", "income"),
        ("balance_sheet", "balance"),
        ("cashflow", "cashflow"),
    ):
        try:
            df = getattr(t, attr)
            if df is not None and not df.empty:
                statements[label] = {
                    "columns": [str(c) for c in df.columns],
                    "rows": {str(idx): [float(v) if v == v else None for v in row]
                             for idx, row in df.iterrows()},
                }
        except Exception:
            continue

    return {
        "ticker": ticker,
        "info": info,
        "valuation_signals": valuation_signals,
        # 종목 분류(C-0)용 다년 실측 신호 — statements보다 앞에 배치해
        # 다운스트림 truncation에서 살아남도록 한다.
        "classification_signals": _classification_signals(info, statements),
        "statements": statements,
    }
