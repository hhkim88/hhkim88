"""Regression tests for debate.citation.

Codifies the entity-hint cross-check added after the META JPMorgan/BofA
mismatch case (committed in e8a84fb). Run via:

    uv run python tests/test_citation.py

Exits 0 on success, 1 on failure. No external test framework required.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from debate.citation import (
    Citation,
    extract_citations,
    verify_citations,
    _extract_entity_hint,
)


_failures: list[str] = []


def _check(label: str, ok: bool, detail: str = "") -> None:
    marker = "✅" if ok else "❌"
    print(f"  {marker} {label}" + (f"  ({detail})" if detail else ""))
    if not ok:
        _failures.append(label)


def test_entity_hint_extraction() -> None:
    print("\n[1] _extract_entity_hint pattern coverage")
    cases = [
        ("24/7 Wall St. (JPMorgan 리포트 인용)", "JPMorgan"),
        ("MarketBeat (Truist 리포트 인용)", "Truist"),
        ("TipRanks/Morgan Stanley", "Morgan Stanley"),
        ("TipRanks(Scotiabank 목표가 상향)", "Scotiabank"),
        ("Yahoo Finance(Morgan Stanley 보도)", "Morgan Stanley"),
        ("Investing.com(Evercore ISI 보도)", "Evercore ISI"),
        # Negative cases — should return None (no third-party hint)
        ("Investing.com", None),
        ("TIKR.com", None),
        ("24/7 Wall St.", None),
        # "24/7" must NOT be treated as slash-separated entity
        ("24/7 Wall St.", None),
    ]
    for label, expected in cases:
        got = _extract_entity_hint(label)
        _check(
            f"{label!r} -> {expected!r}",
            got == expected,
            f"got {got!r}",
        )


def test_meta_jpmorgan_demote() -> None:
    """META Bear cited 'JPMorgan downgrade' but the only matching item
    in the pool was the BofA Trims article. Pre-fix: verified.
    Post-fix: partial with explicit mismatch warning."""
    print("\n[2] META JPMorgan/BofA mismatch — demoted to partial")
    pool = [
        {
            "url": "https://news.example/x1",
            "source_name": "24/7 Wall St.",
            "title": "BofA Trims Meta Platforms Price Target to $820 but Stays Bullish",
            "snippet": "Bank of America cut its target on Meta after Q1 earnings.",
            "published_at": "2026-04-30",
        },
    ]
    text = "주가 [출처: 24/7 Wall St. (JPMorgan 리포트 인용), 2026-04-30]"
    results = verify_citations(extract_citations(text), pool, company="Meta Platforms")
    assert len(results) == 1
    r = results[0]
    _check("status demoted to 'partial'", r.status == "partial", f"status={r.status}")
    _check(
        "warning note mentions 'JPMorgan' entity mismatch",
        any("JPMorgan" in n for n in r.notes),
        f"notes={r.notes}",
    )


def test_positive_control_entity_match() -> None:
    """When entity hint and matched article agree, stay verified."""
    print("\n[3] Positive control — entity hint matches article → verified")
    pool = [
        {
            "url": "https://news.example/x2",
            "source_name": "24/7 Wall St.",
            "title": "JPMorgan Downgrades Meta to Neutral on AI CapEx",
            "snippet": "JPMorgan analysts cited concerns over capex.",
            "published_at": "2026-04-30",
        },
    ]
    text = "주가 [출처: 24/7 Wall St. (JPMorgan 리포트 인용), 2026-04-30]"
    results = verify_citations(extract_citations(text), pool, company="Meta Platforms")
    r = results[0]
    _check("status stays 'verified'", r.status == "verified", f"status={r.status}")


def test_publisher_only_unaffected() -> None:
    """Citations with no third-party hint should behave as before
    (verified via publisher match, no demote)."""
    print("\n[4] Publisher-only citation — no entity hint → unchanged behavior")
    pool = [
        {
            "url": "https://news.example/x3",
            "source_name": "24/7 Wall St.",
            "title": "BofA Trims Meta Platforms Price Target to $820",
            "snippet": "Bank of America trimmed.",
            "published_at": "2026-04-30",
        },
    ]
    text = "주가 [출처: 24/7 Wall St., 2026-04-30]"
    results = verify_citations(extract_citations(text), pool, company="Meta Platforms")
    r = results[0]
    _check("status stays 'verified'", r.status == "verified", f"status={r.status}")
    _check("no entity-mismatch warning emitted", not any("미발견" in n for n in r.notes))


def test_slash_separated_entity() -> None:
    """TipRanks/Morgan Stanley pattern — entity is the second slash token."""
    print("\n[5] Slash-separated 'TipRanks/Morgan Stanley' pattern")
    # Mismatch case
    pool_bad = [
        {
            "url": "https://news.example/x4",
            "source_name": "TipRanks",
            "title": "BofA raises Eaton price target",
            "snippet": "BofA on ETN.",
            "published_at": "2026-04-22",
        },
    ]
    text = "주가 [출처: TipRanks/Morgan Stanley, 2026-04-22]"
    r = verify_citations(extract_citations(text), pool_bad, company="Eaton")[0]
    _check("Morgan Stanley citation vs BofA article → partial", r.status == "partial")

    # Match case
    pool_good = [
        {
            "url": "https://news.example/x5",
            "source_name": "TipRanks",
            "title": "Eaton price target raised to $500 from $425 at Morgan Stanley",
            "snippet": "Morgan Stanley analysts.",
            "published_at": "2026-05-10",
        },
    ]
    text = "주가 [출처: TipRanks/Morgan Stanley, 2026-05-10]"
    r = verify_citations(extract_citations(text), pool_good, company="Eaton")[0]
    _check("Morgan Stanley citation vs Morgan Stanley article → verified", r.status == "verified")


def test_internal_tool_reference_preserved() -> None:
    """Ensure internal-tool references (get_financials, 자체 분석 etc.) still
    end up as 'internal', not partial — entity-hint logic must not interfere."""
    print("\n[6] Internal-tool references stay 'internal' (regression guard)")
    pool: list[dict] = []
    text = "OPM 41% [출처: get_financials 재무데이터 자체 계산, 2026-05-15]"
    r = verify_citations(extract_citations(text), pool, company="Meta Platforms")[0]
    _check("internal-tool citation classified as 'internal'", r.status == "internal")


def main() -> int:
    test_entity_hint_extraction()
    test_meta_jpmorgan_demote()
    test_positive_control_entity_match()
    test_publisher_only_unaffected()
    test_slash_separated_entity()
    test_internal_tool_reference_preserved()

    print()
    if _failures:
        print(f"❌ {len(_failures)} test(s) failed:")
        for f in _failures:
            print(f"  - {f}")
        return 1
    print("✅ All citation regression tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
