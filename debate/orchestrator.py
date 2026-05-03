"""Multi-round Bull vs Bear debate orchestrator (Claude Agent SDK runtime).

Uses claude-agent-sdk which spawns the local `claude` CLI under the hood.
Authentication is inherited from Claude Code (Max subscription). No API key required.
"""

from __future__ import annotations

import anyio
import json
import os
from dataclasses import dataclass, field
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
    ToolUseBlock,
    create_sdk_mcp_server,
    query,
    tool,
)

from .personas import BEAR_SYSTEM, BULL_SYSTEM, MODERATOR_SYSTEM, ROUND_INSTRUCTIONS
from .tools import dispatch as tool_dispatch

DEFAULT_MODEL = os.environ.get("DEBATE_MODEL", "claude-sonnet-4-6")
MODERATOR_MODEL = os.environ.get("MODERATOR_MODEL", "claude-haiku-4-5")
MAX_TURNS = int(os.environ.get("DEBATE_MAX_TURNS", "12"))


# --- in-process MCP tool wrappers ---------------------------------------------

def _wrap(result: Any) -> dict[str, Any]:
    payload = json.dumps(result, default=str, ensure_ascii=False)
    if len(payload) > 25000:
        payload = payload[:25000] + "...[truncated]"
    return {"content": [{"type": "text", "text": payload}]}


@tool(
    "search_company_news",
    "Search recent news about a company. stance='bull'|'bear'|'neutral' biases keyword expansion.",
    {"company": str, "market": str, "stance": str, "limit": int},
)
async def t_search_company_news(args):
    return _wrap(tool_dispatch("search_company_news", args))


@tool(
    "get_financials",
    "Most recent annual financial summary (revenue, op income, net income, assets, equity).",
    {"company": str, "market": str, "year": int},
)
async def t_get_financials(args):
    return _wrap(tool_dispatch("get_financials", args))


@tool(
    "get_price_history",
    "Daily OHLCV history with 52w high/low and % change summary.",
    {"ticker": str, "days": int},
)
async def t_get_price_history(args):
    return _wrap(tool_dispatch("get_price_history", args))


@tool(
    "get_analyst_consensus",
    "Analyst consensus: target price distribution + recommendation breakdown.",
    {"ticker": str, "market": str},
)
async def t_get_analyst_consensus(args):
    return _wrap(tool_dispatch("get_analyst_consensus", args))


@tool(
    "get_secondary_reports",
    "News articles citing brokerage analyst reports.",
    {"company": str, "market": str, "limit": int},
)
async def t_get_secondary_reports(args):
    return _wrap(tool_dispatch("get_secondary_reports", args))


@tool(
    "get_youtube_analysis",
    "Curated investment YouTube channel transcripts.",
    {"company": str, "market": str, "limit": int},
)
async def t_get_youtube_analysis(args):
    return _wrap(tool_dispatch("get_youtube_analysis", args))


@tool(
    "get_social_buzz",
    "Reddit (US) or Naver discussion board (KR) posts.",
    {"company": str, "market": str, "limit": int},
)
async def t_get_social_buzz(args):
    return _wrap(tool_dispatch("get_social_buzz", args))


@tool(
    "get_ir_materials",
    "Company IR filings (KR: DART; US: SEC 8-K).",
    {"company": str, "market": str, "limit": int},
)
async def t_get_ir_materials(args):
    return _wrap(tool_dispatch("get_ir_materials", args))


@tool(
    "get_public_reports",
    "Hankyung Consensus public analyst PDFs (KR only).",
    {"company": str, "limit": int},
)
async def t_get_public_reports(args):
    return _wrap(tool_dispatch("get_public_reports", args))


_TOOLS = [
    t_search_company_news,
    t_get_financials,
    t_get_price_history,
    t_get_analyst_consensus,
    t_get_secondary_reports,
    t_get_youtube_analysis,
    t_get_social_buzz,
    t_get_ir_materials,
    t_get_public_reports,
]
_MCP_NAME = "debate"
_MCP_SERVER = create_sdk_mcp_server(_MCP_NAME, tools=_TOOLS)
_ALLOWED_TOOLS = [f"mcp__{_MCP_NAME}__{t.name}" for t in _TOOLS]


# --- agent runtime ------------------------------------------------------------

@dataclass
class AgentTurn:
    role: str  # "bull" | "bear" | "moderator"
    round_idx: int
    round_kind: str  # "open" | "rebut" | "close" | "moderate"
    text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


async def _agent_run(
    system: str,
    user_msg: str,
    resume_session: str | None,
    model: str,
    use_tools: bool = True,
) -> tuple[str, str | None, list[dict[str, Any]]]:
    """Run one agent turn. Returns (final_text, session_id_for_next_turn, tool_log)."""
    options_kwargs: dict[str, Any] = {
        "system_prompt": system,
        "model": model,
        "max_turns": MAX_TURNS,
        "setting_sources": [],  # do not load user/project settings
    }
    if use_tools:
        options_kwargs["mcp_servers"] = {_MCP_NAME: _MCP_SERVER}
        options_kwargs["allowed_tools"] = _ALLOWED_TOOLS
    if resume_session:
        options_kwargs["resume"] = resume_session

    options = ClaudeAgentOptions(**options_kwargs)

    final_text = ""
    new_session = resume_session
    tool_log: list[dict[str, Any]] = []

    async for msg in query(prompt=user_msg, options=options):
        if isinstance(msg, SystemMessage):
            data = getattr(msg, "data", {}) or {}
            sid = data.get("session_id")
            if sid:
                new_session = sid
        elif isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, ToolUseBlock):
                    tool_log.append(
                        {"name": block.name, "input": block.input, "ok": True}
                    )
        elif isinstance(msg, ResultMessage):
            result_text = getattr(msg, "result", None)
            if result_text:
                final_text = result_text

    return final_text, new_session, tool_log


async def _run_debate_async(
    company: str,
    market: str,
    rounds: int,
    model: str,
) -> list[AgentTurn]:
    transcript: list[AgentTurn] = []
    bull_session: str | None = None
    bear_session: str | None = None
    last_bull_text = ""
    last_bear_text = ""

    if rounds >= 2:
        round_kinds = ["open"] + ["rebut"] * (rounds - 2) + ["close"]
    else:
        round_kinds = ["open"]
    round_kinds = round_kinds[:rounds]

    for i, kind in enumerate(round_kinds, start=1):
        instr = ROUND_INSTRUCTIONS[kind]

        bull_prompt = f"기업: **{company}** (시장: {market})\n\n{instr}"
        if last_bear_text:
            bull_prompt += (
                f"\n\n방금 Bear 애널리스트가 다음과 같이 주장했습니다:\n"
                f"---\n{last_bear_text[:3000]}\n---"
            )
        bull_text, bull_session, bull_tools = await _agent_run(
            BULL_SYSTEM, bull_prompt, bull_session, model
        )
        transcript.append(
            AgentTurn(role="bull", round_idx=i, round_kind=kind, text=bull_text, tool_calls=bull_tools)
        )
        last_bull_text = bull_text

        bear_prompt = f"기업: **{company}** (시장: {market})\n\n{instr}"
        if last_bull_text:
            bear_prompt += (
                f"\n\n방금 Bull 애널리스트가 다음과 같이 주장했습니다:\n"
                f"---\n{last_bull_text[:3000]}\n---"
            )
        bear_text, bear_session, bear_tools = await _agent_run(
            BEAR_SYSTEM, bear_prompt, bear_session, model
        )
        transcript.append(
            AgentTurn(role="bear", round_idx=i, round_kind=kind, text=bear_text, tool_calls=bear_tools)
        )
        last_bear_text = bear_text

    full_dialogue = "\n\n".join(
        f"### Round {t.round_idx} - {t.role.upper()}\n{t.text}" for t in transcript
    )
    mod_prompt = (
        f"기업: **{company}** (시장: {market})\n\n"
        f"아래는 Bull과 Bear 애널리스트의 토론 전문입니다. 정해진 형식대로 정리하세요.\n\n"
        f"---\n{full_dialogue}\n---"
    )
    mod_text, _, _ = await _agent_run(
        MODERATOR_SYSTEM, mod_prompt, None, MODERATOR_MODEL, use_tools=False
    )
    transcript.append(
        AgentTurn(
            role="moderator",
            round_idx=len(round_kinds) + 1,
            round_kind="moderate",
            text=mod_text,
        )
    )
    return transcript


def run_debate(
    company: str,
    market: str = "KR",
    rounds: int = 3,
    model: str = DEFAULT_MODEL,
) -> list[AgentTurn]:
    return anyio.run(_run_debate_async, company, market, rounds, model)
