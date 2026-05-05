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
    status: str  # "verified" | "partial" | "suspect"
    matched_source_name: str | None = None
    matched_title: str | None = None
    matched_url: str | None = None
    notes: list[str] = field(default_factory=list)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def verify_citations(
    citations: list[Citation],
    item_pool: list[dict[str, Any]],
) -> list[VerifiedCitation]:
    """Match every citation against the agent's item pool.

    item_pool is the concatenated list of items from each
    `collect_existing_arguments` call this side made.
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

        # Tier 1: URL exact-or-substring
        if c_url:
            for it in norm_items:
                if it["url"] and (c_url == it["url"] or c_url in it["url"] or it["url"] in c_url):
                    status = "verified"
                    match = it
                    notes.append("URL 일치")
                    break

        # Tier 2: source_name overlap
        if status == "suspect" and c_label:
            for it in norm_items:
                if it["source_name"] and (
                    c_label in it["source_name"] or it["source_name"] in c_label
                ):
                    status = "verified"
                    match = it
                    notes.append("source_name 일치")
                    break

        # Tier 3: label appears in some item's snippet/title.
        # Also try the leading entity-name token of the label, to catch cases
        # like "키움증권 4/22 리포트" where only "키움증권" appears in the snippet.
        candidates: list[str] = []
        if c_label and len(c_label) >= 2:
            candidates.append(c_label)
            head = re.match(r"^[\w가-힣&\.\-]+", c_label)
            if head and head.group(0) and head.group(0) != c_label and len(head.group(0)) >= 2:
                candidates.append(head.group(0))
        if status == "suspect" and candidates:
            for cand in candidates:
                for it in norm_items:
                    if cand in it["snippet"] or cand in it["title"]:
                        status = "partial"
                        match = it
                        notes.append(f"snippet에서 '{cand}' 발견")
                        break
                if status != "suspect":
                    break

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
        return {"verified": "✅", "partial": "⚠️", "suspect": "❌"}.get(status, "?")

    def _summary(verified: list[VerifiedCitation]) -> tuple[int, int, int]:
        v = sum(1 for x in verified if x.status == "verified")
        p = sum(1 for x in verified if x.status == "partial")
        s = sum(1 for x in verified if x.status == "suspect")
        return v, p, s

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
    lines.append("- ❌ **suspect**: 풀 어디에도 매칭 없음 — 학습 데이터 또는 환각 가능성")
    lines.append("")

    for label, pool, verified in [
        ("🐂 Bull", bull_pool, bull_verified),
        ("🐻 Bear", bear_pool, bear_verified),
    ]:
        v, p, s = _summary(verified)
        total = max(len(verified), 1)
        lines.append(f"### {label}")
        lines.append("")
        lines.append(
            f"- 인용 총 **{len(verified)}건**: ✅ {v} / ⚠️ {p} / ❌ {s} "
            f"(검증율 {(v + p) * 100 // total}%)"
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
