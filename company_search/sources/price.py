"""Daily OHLCV history for KR/US tickers via FinanceDataReader."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .. import cache


@cache.cached("price", ttl=12 * 3600)
def get_price_history(ticker: str, days: int = 365) -> dict[str, Any]:
    import FinanceDataReader as fdr

    end = datetime.utcnow().date()
    start = end - timedelta(days=days)
    df = fdr.DataReader(ticker, start, end)
    if df is None or df.empty:
        return {"ticker": ticker, "days": days, "rows": []}
    df = df.reset_index()
    rows = []
    for _, r in df.iterrows():
        rows.append(
            {
                "date": str(r.get("Date", r.get("index", ""))).split(" ")[0],
                "open": float(r.get("Open", 0) or 0),
                "high": float(r.get("High", 0) or 0),
                "low": float(r.get("Low", 0) or 0),
                "close": float(r.get("Close", 0) or 0),
                "volume": float(r.get("Volume", 0) or 0),
            }
        )
    last = rows[-1] if rows else {}
    first = rows[0] if rows else {}
    summary = {}
    if first and last:
        try:
            summary = {
                "first_close": first["close"],
                "last_close": last["close"],
                "pct_change": (last["close"] / first["close"] - 1) * 100
                if first["close"]
                else 0.0,
                "high_52w": max(r["high"] for r in rows),
                "low_52w": min(r["low"] for r in rows if r["low"] > 0),
            }
        except Exception:
            summary = {}
    return {"ticker": ticker, "days": days, "rows": rows, "summary": summary}
