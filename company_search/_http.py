"""HTTP helpers — realistic browser headers and a small polite delay.

The Korean portals (Naver Search, Naver Stock, Hankyung Consensus) actively
block traffic that announces itself as a bot. The previous default UA
("company-search/0.1") was getting 403'd on every request. This module
centralises a desktop/mobile Chrome User-Agent and the standard request
headers a real browser would send, so every scraper can `from .._http
import get_html` and stop reinventing the wheel.
"""

from __future__ import annotations

import random
import time
from typing import Any

import requests

DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
)
MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 13; SM-S918N) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36"
)


def browser_headers(
    referer: str | None = None,
    *,
    mobile: bool = False,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    h = {
        "User-Agent": MOBILE_UA if mobile else DESKTOP_UA,
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    if referer:
        h["Referer"] = referer
    if extra:
        h.update(extra)
    return h


def get_html(
    url: str,
    *,
    mobile: bool = False,
    referer: str | None = None,
    timeout: int = 15,
    extra_headers: dict[str, str] | None = None,
) -> requests.Response:
    """GET with realistic browser headers and a small randomised polite delay."""
    time.sleep(random.uniform(0.3, 0.8))
    r = requests.get(
        url,
        headers=browser_headers(referer, mobile=mobile, extra=extra_headers),
        timeout=timeout,
    )
    r.raise_for_status()
    return r
