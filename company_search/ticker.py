"""Map a free-form company name (e.g. '삼성전자', 'Apple') to a ticker + market."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

import pandas as pd

from . import cache

Market = Literal["KR", "US"]


@dataclass(frozen=True)
class TickerInfo:
    ticker: str
    name: str
    market: Market


@lru_cache(maxsize=2)
def _kr_listing() -> pd.DataFrame:
    cached = cache.get("ticker:kr_listing", ttl=7 * 24 * 3600)
    if cached is not None:
        return pd.DataFrame(cached)
    import FinanceDataReader as fdr

    df = fdr.StockListing("KRX")
    cache.set("ticker:kr_listing", df.to_dict(orient="records"))
    return df


@lru_cache(maxsize=2)
def _us_listing() -> pd.DataFrame:
    cached = cache.get("ticker:us_listing", ttl=7 * 24 * 3600)
    if cached is not None:
        return pd.DataFrame(cached)
    import FinanceDataReader as fdr

    parts = []
    for src in ("NASDAQ", "NYSE", "AMEX"):
        try:
            parts.append(fdr.StockListing(src))
        except Exception:
            continue
    if not parts:
        return pd.DataFrame(columns=["Symbol", "Name"])
    df = pd.concat(parts, ignore_index=True)
    cache.set("ticker:us_listing", df.to_dict(orient="records"))
    return df


def _safe_listing(loader) -> "pd.DataFrame":
    try:
        return loader()
    except Exception:
        return pd.DataFrame()


def resolve(query: str, market: Market | None = None) -> TickerInfo | None:
    """Best-effort resolve. Accepts ticker or company name in either market.
    Falls back gracefully when KRX/NASDAQ listing endpoints are unreachable.
    """
    q = query.strip()

    # 1. Cheap shortcuts that don't need network
    if q.isdigit() and len(q) == 6:
        # Numeric KR ticker (e.g. 005930)
        df = _safe_listing(_kr_listing)
        if not df.empty and "Code" in df.columns:
            match = df[df["Code"].astype(str) == q]
            if not match.empty:
                row = match.iloc[0]
                return TickerInfo(ticker=q, name=row.get("Name", q), market="KR")
        return TickerInfo(ticker=q, name=q, market="KR")

    if market in (None, "US") and q.isascii() and q.isupper() and 1 <= len(q) <= 6:
        return TickerInfo(ticker=q, name=q, market="US")

    # 2. KR name search
    if market in (None, "KR"):
        df = _safe_listing(_kr_listing)
        if not df.empty and "Name" in df.columns:
            code_col = "Code" if "Code" in df.columns else df.columns[0]
            exact = df[df["Name"] == q]
            if not exact.empty:
                row = exact.iloc[0]
                return TickerInfo(ticker=str(row[code_col]), name=row["Name"], market="KR")
            partial = df[df["Name"].str.contains(q, case=False, na=False, regex=False)]
            if not partial.empty:
                row = partial.iloc[0]
                return TickerInfo(ticker=str(row[code_col]), name=row["Name"], market="KR")

    # 3. US name search
    if market in (None, "US"):
        df = _safe_listing(_us_listing)
        if not df.empty:
            sym_col = "Symbol" if "Symbol" in df.columns else df.columns[0]
            if "Name" in df.columns:
                exact = df[df["Name"].str.lower() == q.lower()]
                if not exact.empty:
                    row = exact.iloc[0]
                    return TickerInfo(ticker=str(row[sym_col]), name=row["Name"], market="US")
                partial = df[df["Name"].str.contains(q, case=False, na=False, regex=False)]
                if not partial.empty:
                    row = partial.iloc[0]
                    return TickerInfo(ticker=str(row[sym_col]), name=row["Name"], market="US")
    return None
