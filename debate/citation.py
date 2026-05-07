"""Extract `[출처: ...]` citations from debate turns and verify them against
the items returned by `collect_existing_arguments` calls.

Three-tier verification:
- verified  : URL or source_name match an item exactly (or substring)
- partial   : the cited entity name (e.g., 키움증권) appears in some item's
              snippet/body — the claim probably exists but is being attributed
              to its originator rather than the publishing outlet
- suspect   : no match anywhere in the agent's collected pool — likely
              hallucinated or referenced from training data
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_CITATION_RE = re.compile(r"\[출처\s*[:：]\s*([^\]]+?)\]")
_URL_RE = re.compile(r"https?://[^\s\)\]]+")


@dataclass
class Citation:
    raw: str  # the full text inside [출처: ...]
    source_label: str  # parsed best-effort source label (publisher/broker/channel)
    url: str | None
    date_hint: str | None  # extracted date-like substring if any


def _parse_date_hint(text: str) -> str | None:
    m = re.search(r"\d{4}[-./]\s*\d{1,2}[-./]\s*\d{1,2}", text)
    if m:
        return m.group(0)
    m = re.search(r"\d{4}년\s*\d{1,2}월\s*(?:\d{1,2}일)?", text)
    return m.group(0) if m else None


def extract_citations(text: str) -> list[Citation]:
    """Pull every `[출처: ...]` block from the given text."""
    out: list[Citation] = []
    for m in _CITATION_RE.finditer(text):
        raw = m.group(1).strip()
        url_m = _URL_RE.search(raw)
        url = url_m.group(0).rstrip(".,)]") if url_m else None
        # Strip URL and dates to leave the publisher label
        label = raw
        if url:
            label = label.replace(url, "")
        date = _parse_date_hint(label)
        if date:
            label = label.replace(date, "")
        # Take the first comma-separated chunk as the canonical label
        label = label.replace("|", ",")
        label = label.split(",")[0].strip(" -·:：")
        out.append(Citation(raw=raw, source_label=label, url=url, date_hint=date))
    return out


@dataclass
class VerifiedCitation:
    citation: Citation
    status: str  # "verified" | "partial" | "internal" | "suspect"
    matched_source_name: str | None = None
    matched_title: str | None = None
    matched_url: str | None = None
    notes: list[str] = field(default_factory=list)


def _norm(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip()).lower()
    # Trailing punctuation should not change identity — '@understanding.' and
    # '@understanding' should match each other.
    return s.rstrip(".,;:")


# Substrings that indicate the citation is referring to one of our own internal
# data tools rather than an external item from the collect pool. These citations
# are not hallucinations — the agent is just citing the data tool it called —
# but they shouldn't be matched against the external pool either.
_INTERNAL_TOOL_MARKERS = (
    "mcp__debate__",
    "get_price_history",
    "get_financials",
    "get_analyst_consensus",
    "get_secondary_reports",
    "get_youtube_analysis",
    "get_social_buzz",
    "get_ir_materials",
    "get_public_reports",
    "search_company_news",
    "collect_existing_arguments",
    "finance.naver.com",
    "네이버 파이낸스",
    "네이버 npay",
    "데이터 검증",
    "ohlcv",
    # DART pulls flow through our get_financials tool, so any citation
    # explicitly tagged with DART is an internal-tool self-reference, not
    # an external item from the collect pool.
    "dart 재무",
    "dart 전자공시",
    "dart 사업보고",
    "재무데이터",
    "전자공시",
    "사업연도 영업이익",
    # Price-history citations like "주가 데이터 (005930, 180일 실적)" come
    # from get_price_history; they're a self-reference, not a hallucinated
    # external claim.
    "주가 데이터",
    "가격 히스토리",
    "가격 데이터",
    "180일 실적",
    "365일 실적",
    "180일 데이터",
    "365일 데이터",
    "180일 ohlcv",
    "365일 ohlcv",
    # Analyst self-reference: when the agent attributes a calculation or
    # synthesis to its own work (rather than an external source), it's not
    # a hallucination — there's just nothing in the external pool to match.
    "자체 분석",
    "자체 데이터 분석",
    "자체 계산",
    "자체 검증",
    "자체 합성",
    # Korean natural-language descriptions of the get_analyst_consensus output.
    # Without these the Bear's "애널리스트 컨센서스 데이터, 2026-05-07 기준"
    # falls through to ❌ suspect even though it's a self-reference to the
    # consensus tool, not a hallucinated external source.
    "애널리스트 컨센서스",
    "컨센서스 데이터",
    "컨센서스 집계",
    # Financial-statement self-references. The agent often cites
    # "AAPL Income Statement" or "AAPL Cash Flow Statement, FY2025 기준" —
    # those numbers come from get_financials (yfinance under the hood), not
    # an external pool item. Without these markers the 4-char "AAPL" head
    # falls through to tier-3 partial matching and pairs with random Apple
    # news articles whose snippets happen to contain "Apple".
    "income statement",
    "balance sheet",
    "cash flow statement",
    "financial statements",
    "yahoo finance financial",
    "재무제표",
    "현금흐름표",
    "손익계산서",
    "재무상태표",
)


def _is_internal_tool_reference(raw_label: str, url: str | None) -> bool:
    haystack = f"{raw_label} {url or ''}".lower()
    return any(marker in haystack for marker in _INTERNAL_TOOL_MARKERS)


def _date_compatible(citation_date: str | None, item_date: str) -> bool:
    """Loose date compatibility check. Citation has '2026-01-15' or
    '2026.01.15' or '2026년 1월 15일'. Item published_at is usually
    ISO 8601 like '2026-01-15T10:30:00'."""
    if not citation_date or not item_date:
        return False
    cd = re.sub(r"[^\d]", "-", citation_date).strip("-")
    id_norm = re.sub(r"[^\d]", "-", str(item_date).split("T")[0]).strip("-")
    if not cd or not id_norm:
        return False
    cd_parts = [p for p in cd.split("-") if p]
    id_parts = [p for p in id_norm.split("-") if p]
    if len(cd_parts) < 3 or len(id_parts) < 3:
        return False
    return cd_parts[0] == id_parts[0] and (
        cd_parts[1].lstrip("0") == id_parts[1].lstrip("0")
        and cd_parts[2].lstrip("0") == id_parts[2].lstrip("0")
    )


def _score_candidate(
    citation: Citation,
    item: dict[str, Any],
    company: str | None,
) -> int:
    """Higher = better candidate among multiple publisher matches.

    Same publisher and date can return multiple unrelated articles
    (e.g., 연합인포맥스 2026-01-15 has both a 효성중공업 and a 카카오 article).
    Without disambiguation, the matcher would pick whichever comes first
    in the pool — possibly the wrong one. Score by:
      • date overlap with the citation's date hint
      • debate company name appearing in the item's title
    """
    score = 0
    raw_item = item["raw"]
    if citation.date_hint and _date_compatible(citation.date_hint, raw_item.get("published_at") or ""):
        score += 10
    if company:
        company_norm = _norm(company)
        item_title = _norm(raw_item.get("title") or "")
        item_snippet = _norm(raw_item.get("snippet") or "")
        if company_norm and company_norm in item_title:
            score += 25
        elif company_norm and company_norm in item_snippet:
            score += 5
    return score


def _pick_best(
    candidates: list[dict[str, Any]],
    citation: Citation,
    company: str | None,
) -> dict[str, Any]:
    """Pick the highest-scoring candidate; fall back to the first one."""
    if not candidates:
        raise ValueError("no candidates")
    if len(candidates) == 1:
        return candidates[0]
    return max(candidates, key=lambda it: _score_candidate(citation, it, company))


def verify_citations(
    citations: list[Citation],
    item_pool: list[dict[str, Any]],
    *,
    company: str | None = None,
) -> list[VerifiedCitation]:
    """Match every citation against the agent's item pool.

    item_pool is the concatenated list of items from each
    `collect_existing_arguments` call this side made. ``company`` (the
    debate subject) disambiguates between multiple pool items that share
    the same publisher and date — without it, two articles from the same
    outlet on the same day are matched arbitrarily.
    """
    norm_items = []
    for it in item_pool:
        norm_items.append(
            {
                "raw": it,
                "url": _norm(it.get("url") or ""),
                "source_name": _norm(it.get("source_name") or ""),
                "title": _norm(it.get("title") or ""),
                "snippet": _norm(it.get("snippet") or ""),
            }
        )

    out: list[VerifiedCitation] = []
    for c in citations:
        status = "suspect"
        match = None
        notes: list[str] = []
        c_label = _norm(c.source_label)
        c_url = _norm(c.url or "")

        # Tier 1: URL exact-or-substring — collect all matches, pick best
        if c_url:
            url_matches = [
                it
                for it in norm_items
                if it["url"]
                and (c_url == it["url"] or c_url in it["url"] or it["url"] in c_url)
            ]
            if url_matches:
                match = _pick_best(url_matches, c, company)
                status = "verified"
                notes.append(
                    "URL 일치"
                    + (f" (후보 {len(url_matches)}개 중 회사·날짜 점수 최고)" if len(url_matches) > 1 else "")
                )

        # Tier 2: source_name overlap — collect all, pick best
        if status == "suspect" and c_label:
            sn_matches = [
                it
                for it in norm_items
                if it["source_name"]
                and (c_label in it["source_name"] or it["source_name"] in c_label)
            ]
            if sn_matches:
                match = _pick_best(sn_matches, c, company)
                status = "verified"
                notes.append(
                    "source_name 일치"
                    + (f" (후보 {len(sn_matches)}개 중 회사·날짜 점수 최고)" if len(sn_matches) > 1 else "")
                )

        # Tier 3: label appears in some item's snippet/title.
        # Also try the leading entity-name token of the label, to catch cases
        # like "키움증권 4/22 리포트" where only "키움증권" appears in the snippet.
        if status == "suspect":
            tier3_candidates: list[str] = []
            if c_label and len(c_label) >= 2:
                tier3_candidates.append(c_label)
                head = re.match(r"^[\w가-힣&\.\-]+", c_label)
                if head and head.group(0) and head.group(0) != c_label and len(head.group(0)) >= 2:
                    tier3_candidates.append(head.group(0))
            for cand in tier3_candidates:
                hits = [
                    it for it in norm_items
                    if cand in it["snippet"] or cand in it["title"]
                ]
                if hits:
                    match = _pick_best(hits, c, company)
                    status = "partial"
                    notes.append(f"snippet에서 '{cand}' 발견")
                    break

        # Demote citations to ⚙️ internal when they reference one of our own
        # data tools (price history, DART pulls, "자체 분석" tags). A hybrid
        # citation like "유진투자증권, DS투자증권 리포트 종합, 자체 계산" matches
        # via tier 2 (source_name) and stays ✅ verified above, so this only
        # affects suspect/partial outcomes. Override partial too because tier-3
        # partial matches on short heads like "AAPL" pair with unrelated Apple
        # news articles whose snippets happen to contain "Apple" — internal is
        # the more accurate label when the citation explicitly names a
        # financial-statement or consensus-data self-reference.
        if status in ("suspect", "partial") and _is_internal_tool_reference(c.raw, c.url):
            status = "internal"
            match = None
            notes = ["내부 도구 결과를 출처로 인용 (외부 풀과 무관)"]

        out.append(
            VerifiedCitation(
                citation=c,
                status=status,
                matched_source_name=(match["raw"].get("source_name") if match else None),
                matched_title=(match["raw"].get("title") if match else None),
                matched_url=(match["raw"].get("url") if match else None),
                notes=notes,
            )
        )
    return out


def source_type_distribution(item_pool: list[dict[str, Any]]) -> dict[str, int]:
    """Count items per source_type. Used for diversity reporting."""
    out: dict[str, int] = {}
    for it in item_pool:
        st = it.get("source_type") or "unknown"
        out[st] = out.get(st, 0) + 1
    return out


def render_verification_report(
    bull_pool: list[dict[str, Any]],
    bear_pool: list[dict[str, Any]],
    bull_verified: list[VerifiedCitation],
    bear_verified: list[VerifiedCitation],
) -> str:
    """Render a programmatic verification section as markdown."""

    def _icon(status: str) -> str:
        return {"verified": "✅", "partial": "⚠️", "internal": "⚙️", "suspect": "❌"}.get(
            status, "?"
        )

    def _summary(verified: list[VerifiedCitation]) -> tuple[int, int, int, int]:
        v = sum(1 for x in verified if x.status == "verified")
        p = sum(1 for x in verified if x.status == "partial")
        i = sum(1 for x in verified if x.status == "internal")
        s = sum(1 for x in verified if x.status == "suspect")
        return v, p, i, s

    def _diversity(pool: list[dict[str, Any]]) -> str:
        dist = source_type_distribution(pool)
        if not dist:
            return "_수집된 외부 자료 없음_"
        return ", ".join(f"`{k}`={v}" for k, v in sorted(dist.items()))

    lines = ["## 🔍 인용 검증 보고서", ""]
    lines.append("프로그램이 자동으로 각 인용을 `collect_existing_arguments`가 실제 반환한 ")
    lines.append("items 풀과 대조했습니다. 사회자 LLM이 만든 표가 아니라 코드 기반 검증입니다.")
    lines.append("")
    lines.append("- ✅ **verified**: URL 또는 source_name이 풀의 항목과 일치")
    lines.append("- ⚠️ **partial**: 인용 주체명이 풀 항목의 본문에서만 발견 (간접 인용)")
    lines.append("- ⚙️ **internal**: 내부 도구 결과(get_price_history 등) 자기참조 — 환각 아님")
    lines.append("- ❌ **suspect**: 풀 어디에도 매칭 없음 — 학습 데이터 또는 환각 가능성")
    lines.append("")
    lines.append(
        "_검증율 = (verified + partial) ÷ (suspect 포함 외부 인용 합계). "
        "internal은 외부 인용이 아니므로 분모에서 제외._"
    )
    lines.append("")

    for label, pool, verified in [
        ("🐂 Bull", bull_pool, bull_verified),
        ("🐻 Bear", bear_pool, bear_verified),
    ]:
        v, p, i, s = _summary(verified)
        external_total = v + p + s
        rate = f"{(v + p) * 100 // external_total}%" if external_total else "N/A"
        lines.append(f"### {label}")
        lines.append("")
        lines.append(
            f"- 인용 총 **{len(verified)}건**: ✅ {v} / ⚠️ {p} / ⚙️ {i} / ❌ {s} "
            f"(외부 검증율 {rate})"
        )
        lines.append(f"- 외부 풀 항목 수: **{len(pool)}**개")
        lines.append(f"- 출처 다양성: {_diversity(pool)}")
        if not verified:
            lines.append("- _이 측에서 추출된 인용 없음_")
            lines.append("")
            continue
        lines.append("")
        lines.append("| # | 인용 | 검증 | 매칭된 출처 |")
        lines.append("|---|---|---|---|")
        for i, vc in enumerate(verified, start=1):
            cite = vc.citation.raw
            if len(cite) > 80:
                cite = cite[:77] + "..."
            cite = cite.replace("|", "\\|")
            matched = (
                f"{vc.matched_source_name or ''} — {vc.matched_title or ''}"[:80]
                if vc.status != "suspect"
                else "—"
            ).replace("|", "\\|")
            lines.append(f"| {i} | {cite} | {_icon(vc.status)} {vc.status} | {matched} |")
        lines.append("")

    return "\n".join(lines)
