"""HTML 테이블 파싱 및 숫자 정규화.

38.co.kr 의 HTML 은 옛 방식이라 <table> 이 여러 겹 중첩되어 있다.
'헤더 행의 텍스트'로 데이터 테이블과 각 컬럼을 식별하는 방식으로 견고하게 처리한다.
"""

from __future__ import annotations

import re
from typing import Optional

from bs4 import BeautifulSoup

from . import config


# ---------------------------------------------------------------------------
# 숫자/문자열 정규화
# ---------------------------------------------------------------------------
def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def parse_price(s: str) -> Optional[float]:
    """'15,000원' -> 15000.0 / '-' -> None"""
    if not s:
        return None
    m = re.search(r"-?\d[\d,]*\.?\d*", s.replace(" ", ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def parse_competition(s: str) -> Optional[float]:
    """청약/기관 경쟁률 파싱.

    '1,234.56:1' -> 1234.56 / '852.30 : 1' -> 852.30 / '미달' or '-' -> None
    """
    if not s:
        return None
    s = s.strip()
    if any(x in s for x in ("미달", "미정", "-")) and not re.search(r"\d", s):
        return None
    # ':1' 앞쪽 숫자만 취한다
    head = s.split(":")[0]
    return parse_price(head)


def parse_percent(s: str) -> Optional[float]:
    """'+25.5%' -> 25.5 / '▲12.3' -> 12.3 / '-3.1%' -> -3.1"""
    if not s:
        return None
    s = s.strip()
    sign = -1.0 if ("-" in s or "▼" in s or "하락" in s) else 1.0
    m = re.search(r"\d[\d,]*\.?\d*", s)
    if not m:
        return None
    val = float(m.group(0).replace(",", ""))
    return sign * val


# ---------------------------------------------------------------------------
# 헤더 -> 표준 필드 매핑
# ---------------------------------------------------------------------------
def map_header(header_text: str) -> Optional[str]:
    """헤더 셀 텍스트를 표준 필드명으로 매핑. 우선순위는 config 정의 순서."""
    ht = clean_text(header_text)
    for field, keywords in config.FIELD_KEYWORDS.items():
        for kw in keywords:
            if kw in ht:
                return field
    return None


def _row_cells(tr) -> list[str]:
    cells = tr.find_all(["td", "th"], recursive=False)
    if not cells:  # 일부 페이지는 recursive 필요
        cells = tr.find_all(["td", "th"])
    return [clean_text(c.get_text(" ")) for c in cells]


def _score_as_header(cells: list[str]) -> int:
    """행이 헤더일 가능성 점수 = 표준 필드로 매핑되는 셀 개수."""
    return sum(1 for c in cells if map_header(c))


def find_data_table(soup: BeautifulSoup, required_keywords: list[str]):
    """required_keywords 가 헤더에 모두 포함된 테이블을 찾는다.

    가장 많은 데이터 행을 가진 후보를 반환.
    """
    best = None
    best_rows = -1
    for table in soup.find_all("table"):
        text = clean_text(table.get_text(" "))
        if not all(kw in text for kw in required_keywords):
            continue
        rows = table.find_all("tr")
        if len(rows) > best_rows:
            best = table
            best_rows = len(rows)
    return best


def parse_table(table) -> list[dict]:
    """테이블에서 (헤더 자동 탐지 후) 데이터 행을 dict 리스트로 반환.

    dict 의 key 는 표준 필드명(config.FIELD_KEYWORDS). 매핑 안 되는 컬럼은 버린다.
    원본 텍스트는 그대로 두고, 숫자 정규화는 상위 crawler 단계에서 수행한다.
    """
    rows = table.find_all("tr")
    if not rows:
        return []

    # 헤더 행: 앞쪽 몇 줄 중 매핑 점수가 가장 높은 행
    header_idx, header_cells, best_score = 0, [], -1
    for i, tr in enumerate(rows[:5]):
        cells = _row_cells(tr)
        score = _score_as_header(cells)
        if score > best_score:
            best_score, header_idx, header_cells = score, i, cells

    if best_score < 2:
        return []  # 데이터 테이블로 보기 어려움

    # 컬럼 인덱스 -> 필드명
    col_map: dict[int, str] = {}
    for idx, h in enumerate(header_cells):
        field = map_header(h)
        if field and field not in col_map.values():
            col_map[idx] = field

    records = []
    for tr in rows[header_idx + 1:]:
        cells = _row_cells(tr)
        if len(cells) < 2:
            continue
        # 헤더가 반복되는 행은 건너뜀
        if _score_as_header(cells) >= best_score and len(cells) == len(header_cells):
            continue
        rec = {}
        for idx, field in col_map.items():
            if idx < len(cells):
                rec[field] = cells[idx]
        # 종목명이 없으면 데이터 행이 아님
        if rec.get("name"):
            records.append(rec)
    return records


def parse_fund_page(html: str, page_param: str) -> list[dict]:
    """한 페이지 HTML 을 파싱하여 표준 필드 dict 리스트 반환."""
    soup = BeautifulSoup(html, "lxml")
    sig = config.TABLE_SIGNATURES.get(page_param, ["종목명"])
    table = find_data_table(soup, sig)
    if table is None:
        return []
    return parse_table(table)
