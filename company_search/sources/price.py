"""Daily OHLCV history for KR/US tickers.

Primary source FinanceDataReader; yfinance fallback. FDR's KR coverage is
unreliable — it sometimes raises ("021240.KS invalid symbol or has no
data" for 코웨이), sometimes returns data weeks stale (클래시스 truncated
at 4/17). A single un-guarded fdr.DataReader call therefore either crashed
the price tool outright or silently fed a debate month-old prices.

This module: tries FDR, then yfinance (KR: both .KS / .KQ suffixes),
keeps whichever result is freshest, and never raises — a total failure
degrades to an empty row set with an `errors` field instead of aborting
the debate.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable

from .. import cache

# If the newest row is older than this many days, treat the source as stale
# and keep probing fallbacks for fresher data (covers weekends + holidays).
_STALE_DAYS = 7


def _f(x: Any) -> float:
    """Float-coerce a cell, mapping NaN/None/bad values to 0.0."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    return v if v == v else 0.0  # v != v is True only for NaN


def _rows_from_df(df: Any) -> list[dict[str, Any]]:
    """Normalize a FDR or yfinance OHLCV dataframe into row dicts."""
    df = df.reset_index()
    rows: list[dict[str, Any]] = []
    for _, r in df.iterrows():
        date_val = r.get("Date", r.get("Datetime", r.get("index", "")))
        rows.append(
            {
                "date": str(date_val).split(" ")[0],
                "open": _f(r.get("Open", 0)),
                "high": _f(r.get("High", 0)),
                "low": _f(r.get("Low", 0)),
                "close": _f(r.get("Close", 0)),
                "volume": _f(r.get("Volume", 0)),
            }
        )
    return rows


def _fdr_rows(ticker: str, start: Any, end: Any) -> list[dict[str, Any]]:
    import FinanceDataReader as fdr

    df = fdr.DataReader(ticker, start, end)
    if df is None or df.empty:
        return []
    return _rows_from_df(df)


def _yf_rows(symbol: str, start: Any, end: Any) -> list[dict[str, Any]]:
    import yfinance as yf

    # .history() returns a clean single-level OHLCV frame (DatetimeIndex
    # named 'Date'); yf.download() can return MultiIndex columns.
    df = yf.Ticker(symbol).history(start=start, end=end, auto_adjust=False)
    if df is None or df.empty:
        return []
    return _rows_from_df(df)


def _is_fresh(last_date: str, today: Any) -> bool:
    try:
        d = datetime.strptime(last_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return False
    return (today - d).days <= _STALE_DAYS


@cache.cached("price:v2", ttl=12 * 3600)
def get_price_history(ticker: str, days: int = 365) -> dict[str, Any]:
    end = datetime.utcnow().date()
    start = end - timedelta(days=days)

    is_kr_code = ticker.isdigit() and len(ticker) == 6
    candidates: list[tuple[str, Callable[[], list[dict[str, Any]]]]] = [
        ("fdr", lambda: _fdr_rows(ticker, start, end)),
    ]
    if is_kr_code:
        # FDR's internal yfinance routing guesses the exchange suffix and
        # often guesses wrong; try both KOSPI (.KS) and KOSDAQ (.KQ).
        candidates.append(("yfinance:.KS", lambda: _yf_rows(f"{ticker}.KS", start, end)))
        candidates.append(("yfinance:.KQ", lambda: _yf_rows(f"{ticker}.KQ", start, end)))
    else:
        candidates.append(("yfinance", lambda: _yf_rows(ticker, start, end)))

    best_rows: list[dict[str, Any]] = []
    best_src = ""
    errors: list[str] = []
    for src, fn in candidates:
        try:
            rows = fn()
        except Exception as e:  # FDR/yfinance raise a wide variety of errors
            errors.append(f"{src}: {type(e).__name__}: {e}")
            continue
        if not rows:
            errors.append(f"{src}: empty")
            continue
        if not best_rows or rows[-1]["date"] > best_rows[-1]["date"]:
            best_rows, best_src = rows, src
        # Stop as soon as a source returns data fresh enough to trust.
        if _is_fresh(rows[-1]["date"], end):
            break

    if not best_rows:
        return {"ticker": ticker, "days": days, "rows": [], "errors": errors}

    last, first = best_rows[-1], best_rows[0]
    summary: dict[str, Any] = {}
    try:
        lows = [r["low"] for r in best_rows if r["low"] > 0]
        summary = {
            "first_close": first["close"],
            "last_close": last["close"],
            "pct_change": (last["close"] / first["close"] - 1) * 100
            if first["close"]
            else 0.0,
            "high_52w": max(r["high"] for r in best_rows),
            "low_52w": min(lows) if lows else 0.0,
            "last_date": last["date"],
            "stale": not _is_fresh(last["date"], end),
        }
    except Exception:
        summary = {}

    out: dict[str, Any] = {
        "ticker": ticker,
        "days": days,
        "rows": best_rows,
        "summary": summary,
        "source": best_src,
    }
    if errors:
        out["errors"] = errors  # surfaced even on success, for transparency
    return out
