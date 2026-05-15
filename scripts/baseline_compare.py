"""Compare framework recommendations to simple baseline rules.

Reads debates/*.md and extracts from each:
- 종합 권고 (framework recommendation)
- G (낙관 - 비관)
- 현재가, 컨센서스 평균 목표가
- 현재가 평가 (저평가/적정/고평가)

Compares to baselines:
- (a) consensus_avg / current_price - 1 >= +20% -> BUY
- (b) Forward P/E < 20 AND EPS YoY > +15% -> BUY (skipped if data missing)

Outputs an overlap table. Cells where framework says BUY but rule (a)
disagrees are the cases where the framework adds value beyond consensus
following — these are the proof points (or red flags).

Usage:
    uv run python scripts/baseline_compare.py debates/*.md
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DebateInfo:
    file: str
    company: str | None = None
    market: str | None = None
    rec: str | None = None
    g_pp: int | None = None
    valuation: str | None = None
    current_price: float | None = None
    consensus_avg: float | None = None


# Each pattern is tried in order; first match wins.
PATTERNS = {
    "header": [
        re.compile(r"^# Bull vs Bear 토론: (?P<company>.+?) \((?P<market>KR|US)\)", re.MULTILINE),
    ],
    "rec": [
        re.compile(r"\*\*종합\s*권고\*\*\s*\|\s*\*\*(?P<v>[^|*\n]+?)\*\*"),
    ],
    "g_pp": [
        re.compile(r"\*\*G\s*\([^)]*\)\*\*\s*\|\s*\*\*(?P<v>[+-]?\d+)\s*pp"),
        re.compile(r"G\s*\(낙관[^)]*\)\s*\|\s*([+-]?\d+)\s*pp"),
    ],
    "valuation": [
        re.compile(r"\*\*현재가\s*평가\*\*\s*\|\s*\*\*(?P<v>[^|*\n]+?)\*\*"),
    ],
    "current_price": [
        # 현재가 followed within 20 chars by $ on the same line/cell
        re.compile(r"현재가[^\n|]{0,20}~?[\$₩](?P<v>[\d,]+\.?\d*)"),
    ],
    "consensus_avg": [
        # Strict: $ immediately follows "평균" (no intervening text)
        re.compile(r"컨센서스\s*평균\s*~?[\$₩](?P<v>[\d,]+\.?\d*)"),
        re.compile(r"목표(?:주가|가)\s*평균\s*~?[\$₩](?P<v>[\d,]+\.?\d*)"),
        re.compile(r"평균\s*목표(?:주가|가)\s*~?[\$₩](?P<v>[\d,]+\.?\d*)"),
        re.compile(r"Avg\s*[:=]?\s*[\$₩](?P<v>[\d,]+\.?\d*)"),
    ],
}


def _to_float(s: str) -> float | None:
    try:
        return float(s.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def parse_debate(path: Path) -> DebateInfo:
    text = path.read_text(encoding="utf-8")
    info = DebateInfo(file=path.name)

    for pat in PATTERNS["header"]:
        m = pat.search(text)
        if m:
            info.company = m.group("company").strip()
            info.market = m.group("market")
            break

    for key in ("rec", "valuation"):
        for pat in PATTERNS[key]:
            m = pat.search(text)
            if m:
                setattr(info, key, m.group("v" if "v" in pat.groupindex else 1).strip())
                break

    for pat in PATTERNS["g_pp"]:
        m = pat.search(text)
        if m:
            info.g_pp = int(m.group("v" if "v" in pat.groupindex else 1))
            break

    for pat in PATTERNS["current_price"]:
        m = pat.search(text)
        if m:
            info.current_price = _to_float(m.group("v" if "v" in pat.groupindex else 1))
            break

    for pat in PATTERNS["consensus_avg"]:
        m = pat.search(text)
        if m:
            info.consensus_avg = _to_float(m.group("v" if "v" in pat.groupindex else 1))
            break

    return info


def is_framework_buy(rec: str | None) -> bool | None:
    if not rec:
        return None
    return "매수" in rec


def rule_a_buy(current: float | None, avg: float | None) -> bool | None:
    if not current or not avg:
        return None
    return (avg / current - 1) >= 0.20


def main(args: list[str]) -> int:
    paths: list[Path] = []
    for a in args:
        paths.extend(Path().glob(a))
    if not paths:
        print("No files matched.", file=sys.stderr)
        return 1

    rows = [parse_debate(p) for p in sorted(paths)]

    hdr = f"{'Company':<22} {'G':>6} {'Framework':<14} {'Cur':>9} {'Avg':>9} {'Upside':>8} {'Rule(a)':<10} {'Diff'}"
    print(hdr)
    print("-" * len(hdr))

    agree_buy = agree_no = framework_only = rule_only = unknown = 0

    for r in rows:
        cur, avg = r.current_price, r.consensus_avg
        upside = (avg / cur - 1) * 100 if (cur and avg) else None
        fw_buy = is_framework_buy(r.rec)
        ra_buy = rule_a_buy(cur, avg)

        if fw_buy is None or ra_buy is None:
            diff = "?"
            unknown += 1
        elif fw_buy and ra_buy:
            diff = "agree-BUY"
            agree_buy += 1
        elif (not fw_buy) and (not ra_buy):
            diff = "agree-no"
            agree_no += 1
        elif fw_buy and not ra_buy:
            diff = "FW-only"
            framework_only += 1
        else:
            diff = "RULE-only"
            rule_only += 1

        company = (r.company or r.file)[:20]
        g = f"{r.g_pp:+d}" if r.g_pp is not None else "?"
        fr = (r.rec or "?")[:12]
        cs = f"{cur:.2f}" if cur else "?"
        ag = f"{avg:.2f}" if avg else "?"
        up = f"{upside:+.1f}%" if upside is not None else "?"
        ra = "BUY" if ra_buy else ("NO" if ra_buy is False else "?")
        print(f"{company:<22} {g:>6} {fr:<14} {cs:>9} {ag:>9} {up:>8} {ra:<10} {diff}")

    total = len(rows)
    print()
    print(f"Total: {total} | agree-BUY: {agree_buy} | agree-no: {agree_no} | "
          f"FW-only BUY: {framework_only} | RULE-only BUY: {rule_only} | unknown: {unknown}")
    print()
    print("FW-only BUY = framework recommends buy when consensus +20% rule does not.")
    print("RULE-only BUY = consensus +20% rule recommends buy when framework does not.")
    print("These two columns are the cases where the framework adds (or loses) value.")
    print("If both are near zero, the framework is largely a 'consensus follower'.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
