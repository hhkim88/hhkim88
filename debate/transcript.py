"""Render a debate transcript to Markdown."""

from __future__ import annotations

from datetime import datetime

from .orchestrator import AgentTurn

ROLE_HEADER = {
    "bull": "🐂 Bull 애널리스트",
    "bear": "🐻 Bear 애널리스트",
    "moderator": "⚖️ Moderator",
    "verification": "🔍 인용 검증",
}

KIND_LABEL = {
    "open": "개진",
    "rebut": "반박",
    "close": "마무리",
    "moderate": "종합",
    "verify": "검증",
}


def to_markdown(company: str, market: str, transcript: list[AgentTurn]) -> str:
    """Render transcript with structured summary + verification report at top,
    full debate log below."""
    parts = [
        f"# Bull vs Bear 토론: {company} ({market})",
        f"_{datetime.utcnow().isoformat(timespec='seconds')}Z_",
        "",
    ]

    moderator_turn = next((t for t in transcript if t.role == "moderator"), None)
    verification_turn = next((t for t in transcript if t.role == "verification"), None)

    if moderator_turn:
        parts.append("---")
        parts.append("## ⚖️ 사회자 종합 (요약)")
        parts.append("")
        parts.append(moderator_turn.text)
        parts.append("")
        parts.append("---")
        parts.append("")

    if verification_turn:
        parts.append(verification_turn.text)
        parts.append("")
        parts.append("---")
        parts.append("")

    parts.append("## 📝 토론 전문 (자유 논쟁)")
    parts.append("")
    for turn in transcript:
        if turn.role in ("moderator", "verification"):
            continue
        header = ROLE_HEADER.get(turn.role, turn.role)
        kind = KIND_LABEL.get(turn.round_kind, turn.round_kind)
        parts.append(f"### Round {turn.round_idx} — {header} ({kind})")
        if turn.tool_calls:
            tool_summary = ", ".join(
                f"`{tc['name']}`{'✓' if tc.get('ok') else '✗'}" for tc in turn.tool_calls
            )
            parts.append(f"_도구 호출: {tool_summary}_")
            parts.append("")
        parts.append(turn.text)
        parts.append("")
    return "\n".join(parts)
