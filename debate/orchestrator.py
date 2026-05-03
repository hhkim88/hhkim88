"""Multi-round Bull vs Bear debate orchestrator."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from anthropic import Anthropic

from .personas import BEAR_SYSTEM, BULL_SYSTEM, MODERATOR_SYSTEM, ROUND_INSTRUCTIONS
from .tools import TOOL_SCHEMAS, dispatch

DEFAULT_MODEL = os.environ.get("DEBATE_MODEL", "claude-sonnet-4-6")
MODERATOR_MODEL = os.environ.get("MODERATOR_MODEL", "claude-haiku-4-5-20251001")
MAX_TOOL_TURNS = 6


@dataclass
class AgentTurn:
    role: str  # "bull" | "bear" | "moderator"
    round_idx: int
    round_kind: str  # "open" | "rebut" | "close" | "moderate"
    text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


def _agent_run(
    client: Anthropic,
    system: str,
    user_msg: str,
    prior_messages: list[dict[str, Any]] | None = None,
    model: str = DEFAULT_MODEL,
    max_tool_turns: int = MAX_TOOL_TURNS,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """Run an agent with tool use until it produces a final text answer.

    Returns: (final_text, full_message_history, tool_call_log)
    """
    messages = list(prior_messages or [])
    messages.append({"role": "user", "content": user_msg})
    tool_log: list[dict[str, Any]] = []

    for _ in range(max_tool_turns):
        resp = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )
        # Append the assistant turn
        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason != "tool_use":
            # Aggregate text blocks
            final = "\n".join(
                block.text for block in resp.content if getattr(block, "type", "") == "text"
            )
            return final, messages, tool_log

        # Execute every tool_use block, append a single user message with tool_results
        tool_results = []
        for block in resp.content:
            if getattr(block, "type", "") != "tool_use":
                continue
            try:
                result = dispatch(block.name, block.input or {})
            except Exception as e:
                result = {"error": str(e)}
            tool_log.append({"name": block.name, "input": block.input, "ok": "error" not in (result if isinstance(result, dict) else {})})
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, default=str, ensure_ascii=False)[:25000],
                }
            )
        messages.append({"role": "user", "content": tool_results})

    return "[max tool turns reached]", messages, tool_log


def run_debate(
    company: str,
    market: str = "KR",
    rounds: int = 3,
    model: str = DEFAULT_MODEL,
) -> list[AgentTurn]:
    client = Anthropic()
    transcript: list[AgentTurn] = []

    bull_history: list[dict[str, Any]] = []
    bear_history: list[dict[str, Any]] = []

    round_kinds = ["open"] + ["rebut"] * (rounds - 2) + ["close"] if rounds >= 2 else ["open"]
    round_kinds = round_kinds[:rounds]

    last_bull_text = ""
    last_bear_text = ""

    for i, kind in enumerate(round_kinds, start=1):
        instr = ROUND_INSTRUCTIONS[kind]

        bull_prompt = f"기업: **{company}** (시장: {market})\n\n{instr}"
        if last_bear_text:
            bull_prompt += f"\n\n방금 Bear 애널리스트가 다음과 같이 주장했습니다:\n---\n{last_bear_text[:3000]}\n---"
        bull_text, bull_history, bull_tools = _agent_run(
            client, BULL_SYSTEM, bull_prompt, prior_messages=bull_history, model=model
        )
        transcript.append(
            AgentTurn(role="bull", round_idx=i, round_kind=kind, text=bull_text, tool_calls=bull_tools)
        )
        last_bull_text = bull_text

        bear_prompt = f"기업: **{company}** (시장: {market})\n\n{instr}"
        if last_bull_text:
            bear_prompt += f"\n\n방금 Bull 애널리스트가 다음과 같이 주장했습니다:\n---\n{last_bull_text[:3000]}\n---"
        bear_text, bear_history, bear_tools = _agent_run(
            client, BEAR_SYSTEM, bear_prompt, prior_messages=bear_history, model=model
        )
        transcript.append(
            AgentTurn(role="bear", round_idx=i, round_kind=kind, text=bear_text, tool_calls=bear_tools)
        )
        last_bear_text = bear_text

    # Moderator summary (no tools — pure synthesis)
    full_dialogue = "\n\n".join(
        f"### Round {t.round_idx} - {t.role.upper()}\n{t.text}" for t in transcript
    )
    mod_prompt = (
        f"기업: **{company}** (시장: {market})\n\n"
        f"아래는 Bull과 Bear 애널리스트의 토론 전문입니다. 정해진 형식대로 정리하세요.\n\n"
        f"---\n{full_dialogue}\n---"
    )
    mod_resp = client.messages.create(
        model=MODERATOR_MODEL,
        max_tokens=3000,
        system=MODERATOR_SYSTEM,
        messages=[{"role": "user", "content": mod_prompt}],
    )
    mod_text = "\n".join(b.text for b in mod_resp.content if getattr(b, "type", "") == "text")
    transcript.append(
        AgentTurn(role="moderator", round_idx=len(round_kinds) + 1, round_kind="moderate", text=mod_text)
    )

    return transcript
