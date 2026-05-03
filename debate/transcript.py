"""Render a debate transcript to Markdown."""

from __future__ import annotations

from datetime import datetime

from .orchestrator import AgentTurn

ROLE_HEADER = {
    "bull": "🐂 Bull 애널리스트",
    "bear": "🐻 Bear 애널리스트",
    "moderator": "⚖️ Moderator",
}

KIND_LABEL = {
    "open": "개진",
    "rebut": "반박",
    "close": "마무리",
    "moderate": "종합",
}


def to_markdown(company: str, market: str, transcript: list[AgentTurn]) -> str:
    parts = [
        f"# Bull vs Bear 토론: {company} ({market})",
        f"_{datetime.utcnow().isoformat(timespec='seconds')}Z_",
        "",
    ]
    for turn in transcript:
        header = ROLE_HEADER.get(turn.role, turn.role)
        kind = KIND_LABEL.get(turn.round_kind, turn.round_kind)
        parts.append(f"## Round {turn.round_idx} — {header} ({kind})")
        if turn.tool_calls:
            tool_summary = ", ".join(
                f"`{tc['name']}`{'✓' if tc.get('ok') else '✗'}" for tc in turn.tool_calls
            )
            parts.append(f"_도구 호출: {tool_summary}_\n")
        parts.append(turn.text)
        parts.append("")
    return "\n".join(parts)
