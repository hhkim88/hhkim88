"""Macro/industry context: Bank of Korea ECOS + FRED."""

from __future__ import annotations

import os
from typing import Any

import requests

from .. import cache


@cache.cached("macro:fred", ttl=24 * 3600)
def fred_series(series_id: str, observations: int = 24) -> dict[str, Any]:
    key = os.environ.get("FRED_API_KEY", "").strip()
    if not key:
        return {"series_id": series_id, "error": "FRED_API_KEY not set"}
    r = requests.get(
        "https://api.stlouisfed.org/fred/series/observations",
        params={
            "series_id": series_id,
            "api_key": key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": observations,
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


@cache.cached("macro:ecos", ttl=24 * 3600)
def ecos_series(stat_code: str, item_code: str, count: int = 24, period: str = "M") -> dict[str, Any]:
    key = os.environ.get("ECOS_API_KEY", "").strip()
    if not key:
        return {"stat_code": stat_code, "error": "ECOS_API_KEY not set"}
    url = (
        f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/{count}/"
        f"{stat_code}/{period}/{item_code}/"
    )
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    return r.json()


# Convenience presets
COMMON_FRED = {
    "us_cpi": "CPIAUCSL",
    "us_unemployment": "UNRATE",
    "us_fed_rate": "FEDFUNDS",
    "us_10y_yield": "DGS10",
    "us_gdp": "GDP",
}
COMMON_ECOS = {
    "kr_base_rate": ("722Y001", "0101000"),
    "kr_cpi": ("901Y009", "0"),
}


def get_macro_snapshot(market: str = "US") -> dict[str, Any]:
    out: dict[str, Any] = {"market": market}
    if market == "US":
        for label, sid in COMMON_FRED.items():
            out[label] = fred_series(sid, observations=6)
    else:
        for label, (stat, item) in COMMON_ECOS.items():
            out[label] = ecos_series(stat, item, count=6)
    return out
