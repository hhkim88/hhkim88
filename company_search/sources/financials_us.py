"""US fundamentals via yfinance."""

from __future__ import annotations

from typing import Any

from .. import cache


@cache.cached("yf:fundamentals", ttl=24 * 3600)
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
            "recommendationKey",
            "targetMeanPrice",
            "currentPrice",
        ]
        info = {k: raw.get(k) for k in keep if k in raw}
    except Exception as e:
        info = {"error": str(e)}

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

    return {"ticker": ticker, "info": info, "statements": statements}
