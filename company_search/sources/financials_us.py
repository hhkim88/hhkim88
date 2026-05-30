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


@cache.cached("yf:fundamentals:v2", ttl=24 * 3600)
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
        "statements": statements,
    }
