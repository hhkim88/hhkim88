"""HTTP 요청 및 인코딩 처리.

38.co.kr 는 EUC-KR/CP949 인코딩이므로 응답 바이트를 직접 디코딩한다.
네트워크 오류 시 지수 백오프로 재시도한다.
"""

from __future__ import annotations

import time

import requests

from . import config


class FetchError(RuntimeError):
    """페이지를 가져오지 못했을 때 발생."""


def _decode(content: bytes) -> str:
    """알려진 인코딩 후보로 순차 디코딩 시도."""
    for enc in config.ENCODINGS:
        try:
            return content.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    # 최후의 보루: 오류 무시 디코딩
    return content.decode(config.ENCODINGS[0], errors="replace")


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": config.USER_AGENT, "Accept-Language": "ko,en;q=0.8"})
    return s


def fetch_page(
    page_param: str,
    page: int = 1,
    session: requests.Session | None = None,
) -> str:
    """38.co.kr fund 페이지 1개를 가져와 디코딩된 HTML 문자열로 반환.

    Parameters
    ----------
    page_param: 'o' 파라미터 값 (예: 'k', 'r').
    page: 페이지 번호 (1부터).
    """
    sess = session or make_session()
    params = {"o": page_param, "page": page}

    last_err: Exception | None = None
    for attempt in range(config.MAX_RETRIES):
        try:
            resp = sess.get(
                config.BASE_URL,
                params=params,
                timeout=config.REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            return _decode(resp.content)
        except requests.RequestException as exc:  # 네트워크/HTTP 오류
            last_err = exc
            wait = 2 ** attempt  # 1, 2, 4, 8 ...
            time.sleep(wait)

    raise FetchError(
        f"페이지 가져오기 실패 (o={page_param}, page={page}): {last_err}"
    )
