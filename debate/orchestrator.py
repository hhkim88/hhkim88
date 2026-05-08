"""Multi-round Bull vs Bear debate orchestrator (Claude Agent SDK runtime).

Uses claude-agent-sdk which spawns the local `claude` CLI under the hood.
Authentication is inherited from Claude Code (Max subscription). No API key required.
"""

from __future__ import annotations

import anyio
import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    create_sdk_mcp_server,
    query,
    tool,
)

from .personas import BEAR_SYSTEM, BULL_SYSTEM, MODERATOR_SYSTEM, ROUND_INSTRUCTIONS
from .tools import dispatch as tool_dispatch
from .argument_collector import collect_existing_arguments as _collect_args
from .citation import (
    extract_citations,
    render_verification_report,
    source_type_distribution,
    verify_citations,
)

DEFAULT_MODEL = os.environ.get("DEBATE_MODEL", "claude-sonnet-4-6")
MODERATOR_MODEL = os.environ.get("MODERATOR_MODEL", "claude-sonnet-4-6")
MAX_TURNS = int(os.environ.get("DEBATE_MAX_TURNS", "12"))


# --- in-process MCP tool wrappers ---------------------------------------------

def _wrap(result: Any) -> dict[str, Any]:
    payload = json.dumps(result, default=str, ensure_ascii=False)
    if len(payload) > 25000:
        payload = payload[:25000] + "...[truncated]"
    return {"content": [{"type": "text", "text": payload}]}


_FAILURE_HINTS = ("403 client error", "404 client error", "host not in allowlist",
                  "forbidden for url", "no data found", "invalid symbol")


def _block_text(block: ToolResultBlock) -> str:
    content = block.content
    if content is None:
        return ""
    if isinstance(content, list):
        return " ".join(
            str(item.get("text", "")) for item in content if isinstance(item, dict)
        )
    return str(content)


_PAYLOAD_KEYS = ("items", "data", "summary", "body", "body_md", "rows", "results")
_META_KEYS = ("company", "market", "stance", "ticker", "counts", "errors", "note")


def _structured_is_substantive(data: Any) -> bool:
    """True if a parsed JSON value carries real, quotable content."""
    if isinstance(data, list):
        meaningful = [d for d in data if not (isinstance(d, dict) and "error" in d and len(d) <= 2)]
        return len(meaningful) > 0
    if isinstance(data, dict):
        # If the response uses any standard payload key, those keys decide.
        payload_keys = [k for k in _PAYLOAD_KEYS if k in data]
        if payload_keys:
            for k in payload_keys:
                v = data[k]
                if isinstance(v, list) and len(v) > 0:
                    return True
                if isinstance(v, dict) and len(v) > 0:
                    return True
                if isinstance(v, str) and len(v) > 80:
                    return True
            return False  # all payload keys present but empty
        if "error" in data and len(data) <= 2:
            return False
        non_meta = [k for k in data if k not in _META_KEYS]
        return len(non_meta) > 0
    return False


def _result_block_is_failure(block: ToolResultBlock) -> bool:
    if block.is_error:
        return True
    text = _block_text(block).strip()
    if not text or text in {"{}", "[]", "null"}:
        return True
    # If the result parses as JSON, trust the structural verdict — don't
    # fall back to substring matching, otherwise per-source error notes in
    # an otherwise-successful aggregator response will produce false negatives.
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        # Plain text: short content or known failure phrases mean failure
        if len(text) < 80:
            return True
        lower = text.lower()
        return any(hint in lower for hint in _FAILURE_HINTS)
    return not _structured_is_substantive(data)


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


@tool(
    "get_earnings_calls",
    "Free earnings call transcripts (US only — Motley Fool). Body is the actual CEO/CFO Q&A. KR returns explanatory error (no free Korean equivalent).",
    {"company": str, "market": str, "limit": int},
)
async def t_get_earnings_calls(args):
    return _wrap(tool_dispatch("get_earnings_calls", args))


@tool(
    "get_seeking_alpha",
    "Seeking Alpha contributor commentary headlines + Google News snippets (US only). stance='bull'|'bear'|'neutral' biases the article filter.",
    {"company": str, "stance": str, "limit": int},
)
async def t_get_seeking_alpha(args):
    return _wrap(tool_dispatch("get_seeking_alpha", args))


@tool(
    "collect_existing_arguments",
    "강세/약세 외부 주장을 한 번에 수집한다. stance에 맞춰 뉴스 키워드를 편향시키고 "
    "secondary 리포트 인용 기사 / 한경 컨센서스 PDF (KR) / 유튜브 분석 / 종토방·Reddit "
    "글을 정규화된 형태로 묶어 반환. 토론 첫 턴에 반드시 호출해서 자체 합성이 아닌 "
    "실재 주장을 인용·반박할 것.",
    {"company": str, "market": str, "stance": str, "per_source_limit": int},
)
async def t_collect_existing_arguments(args):
    out = _collect_args(
        args["company"],
        market=args.get("market", "KR"),
        stance=args.get("stance", "bull"),
        per_source_limit=args.get("per_source_limit", 4),
    )
    return _wrap(out)


_TOOLS = [
    t_collect_existing_arguments,
    t_search_company_news,
    t_get_financials,
    t_get_price_history,
    t_get_analyst_consensus,
    t_get_secondary_reports,
    t_get_youtube_analysis,
    t_get_social_buzz,
    t_get_ir_materials,
    t_get_public_reports,
    t_get_earnings_calls,
    t_get_seeking_alpha,
]
_MCP_NAME = "debate"
_MCP_SERVER = create_sdk_mcp_server(_MCP_NAME, tools=_TOOLS)
_ALLOWED_TOOLS = [f"mcp__{_MCP_NAME}__{t.name}" for t in _TOOLS]

# Tools whose returned items should populate the verification pool. Includes
# collect_existing_arguments (the curated bundle) AND every individual source
# tool the agent might call later for fact-checking. Without this set, a bull
# rebuttal that runs search_company_news(stance="bear") and quotes the result
# would be flagged as ❌ suspect even though the citation is real.
_POOL_TOOL_NAMES = {
    f"mcp__{_MCP_NAME}__collect_existing_arguments",
    f"mcp__{_MCP_NAME}__search_company_news",
    f"mcp__{_MCP_NAME}__get_secondary_reports",
    f"mcp__{_MCP_NAME}__get_public_reports",
    f"mcp__{_MCP_NAME}__get_youtube_analysis",
    f"mcp__{_MCP_NAME}__get_social_buzz",
    f"mcp__{_MCP_NAME}__get_ir_materials",
    f"mcp__{_MCP_NAME}__get_earnings_calls",
    f"mcp__{_MCP_NAME}__get_seeking_alpha",
}


# --- agent runtime ------------------------------------------------------------

@dataclass
class AgentTurn:
    role: str  # "bull" | "bear" | "moderator" | "verification"
    round_idx: int
    round_kind: str  # "open" | "rebut" | "close" | "moderate" | "verify"
    text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


async def _agent_run(
    system: str,
    user_msg: str,
    resume_session: str | None,
    model: str,
    use_tools: bool = True,
) -> tuple[str, str | None, list[dict[str, Any]], list[dict[str, Any]]]:
    """Run one agent turn.

    Returns:
        (final_text, session_id_for_next_turn, tool_log, collect_args_items)
        where collect_args_items is the concatenated `items` array from any
        `collect_existing_arguments` tool calls made during this turn.
    """
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
    last_assistant_text = ""
    new_session = resume_session
    tool_log: list[dict[str, Any]] = []
    by_use_id: dict[str, dict[str, Any]] = {}
    collect_items: list[dict[str, Any]] = []

    async for msg in query(prompt=user_msg, options=options):
        if isinstance(msg, SystemMessage):
            data = getattr(msg, "data", {}) or {}
            sid = data.get("session_id")
            if sid:
                new_session = sid
        elif isinstance(msg, AssistantMessage):
            text_parts: list[str] = []
            for block in msg.content:
                if isinstance(block, ToolUseBlock):
                    entry = {
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                        "ok": None,
                    }
                    tool_log.append(entry)
                    by_use_id[block.id] = entry
                elif isinstance(block, TextBlock):
                    text_parts.append(block.text)
            if text_parts:
                # Each AssistantMessage = one model turn. The LAST one carries
                # the final answer (after any tool calls). Overwriting is correct.
                last_assistant_text = "".join(text_parts)
        elif isinstance(msg, UserMessage):
            content = msg.content
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, ToolResultBlock):
                        entry = by_use_id.get(block.tool_use_id)
                        if entry is not None:
                            entry["ok"] = not _result_block_is_failure(block)
                            # Recover items from any tool that contributes to
                            # the verification pool (collect + every source
                            # search/fetch tool). Even if status flapped to
                            # failure, populated items are still useful.
                            if entry["name"] in _POOL_TOOL_NAMES:
                                items = _parse_pool_items(entry["name"], block.content)
                                if items:
                                    collect_items.extend(items)
                                    entry["ok"] = True
        elif isinstance(msg, ResultMessage):
            result_text = getattr(msg, "result", None)
            if result_text:
                final_text = result_text

    # AssistantMessage TextBlocks contain the model's actual generated output.
    # ResultMessage.result is sometimes truncated for long responses (Sonnet 4.6
    # was observed to lose all but the last ~1000 chars), so prefer the
    # AssistantMessage text when present.
    if last_assistant_text:
        final_text = last_assistant_text

    for entry in tool_log:
        if entry["ok"] is None:
            entry["ok"] = False

    return final_text, new_session, tool_log, collect_items


def _parse_pool_items(tool_name: str, content: Any) -> list[dict[str, Any]]:
    """Extract pool items from any pool-contributing tool result.

    Two payload shapes:
    - collect_existing_arguments wraps a list as ``{"items": [...]}``
    - every other source tool (search_company_news, get_secondary_reports,
      get_public_reports, get_youtube_analysis, get_social_buzz,
      get_ir_materials) returns a flat ``list[CompanyDoc.to_dict()]``.

    Both shapes get normalised into the same dict layout that
    argument_collector emits, so verification matches them uniformly.
    """
    if isinstance(content, list):
        text = " ".join(
            str(item.get("text", "")) for item in content if isinstance(item, dict)
        )
    elif isinstance(content, str):
        text = content
    else:
        return []
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return []

    if tool_name.endswith("__collect_existing_arguments"):
        if isinstance(data, dict):
            items = data.get("items", [])
            return items if isinstance(items, list) else []
        return []

    # Source-tool format: list of CompanyDoc dicts
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for doc in data:
        if not isinstance(doc, dict):
            continue
        if "error" in doc and len(doc) <= 2:
            continue
        metadata = doc.get("metadata") or {}
        source_name = (
            metadata.get("publisher")
            or metadata.get("feed_source")
            or metadata.get("channel")
            or metadata.get("subreddit")
            or metadata.get("platform")
            or metadata.get("broker")
            or doc.get("source")
            or ""
        )
        body = (doc.get("body_md") or "").strip()
        out.append(
            {
                "source_type": doc.get("source") or "external",
                "source_name": str(source_name),
                "title": (doc.get("title") or "").strip(),
                "snippet": body[:600] + ("..." if len(body) > 600 else ""),
                "url": doc.get("url") or "",
                "published_at": doc.get("published_at"),
            }
        )
    return out


# Back-compat alias — argument_collector still imports this name in tests
_parse_collect_items = _parse_pool_items


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
    bull_pool: list[dict[str, Any]] = []  # collect_existing_arguments items, accumulated across rounds
    bear_pool: list[dict[str, Any]] = []

    if rounds >= 2:
        round_kinds = ["open"] + ["rebut"] * (rounds - 2) + ["close"]
    else:
        round_kinds = ["open"]
    round_kinds = round_kinds[:rounds]

    for i, kind in enumerate(round_kinds, start=1):
        instr = ROUND_INSTRUCTIONS[kind]

        if kind == "open":
            # Opening statements are independent — run Bull and Bear concurrently.
            # In real debates each side presents their case without yet responding
            # to the other; rebuttal phase comes next.
            bull_prompt = f"기업: **{company}** (시장: {market})\n\n{instr}"
            bear_prompt = f"기업: **{company}** (시장: {market})\n\n{instr}"
            (
                (bull_text, bull_session, bull_tools, bull_round_items),
                (bear_text, bear_session, bear_tools, bear_round_items),
            ) = await asyncio.gather(
                _agent_run(BULL_SYSTEM, bull_prompt, bull_session, model),
                _agent_run(BEAR_SYSTEM, bear_prompt, bear_session, model),
            )
            bull_pool.extend(bull_round_items)
            bear_pool.extend(bear_round_items)
            transcript.append(
                AgentTurn(role="bull", round_idx=i, round_kind=kind, text=bull_text, tool_calls=bull_tools)
            )
            transcript.append(
                AgentTurn(role="bear", round_idx=i, round_kind=kind, text=bear_text, tool_calls=bear_tools)
            )
            last_bull_text = bull_text
            last_bear_text = bear_text
            continue

        # Rebuttal/closing rounds depend on the prior turn — sequential.
        bull_prompt = f"기업: **{company}** (시장: {market})\n\n{instr}"
        if last_bear_text:
            bull_prompt += (
                f"\n\n방금 Bear 애널리스트가 다음과 같이 주장했습니다:\n"
                f"---\n{last_bear_text[:3000]}\n---"
            )
        bull_text, bull_session, bull_tools, bull_round_items = await _agent_run(
            BULL_SYSTEM, bull_prompt, bull_session, model
        )
        bull_pool.extend(bull_round_items)
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
        bear_text, bear_session, bear_tools, bear_round_items = await _agent_run(
            BEAR_SYSTEM, bear_prompt, bear_session, model
        )
        bear_pool.extend(bear_round_items)
        transcript.append(
            AgentTurn(role="bear", round_idx=i, round_kind=kind, text=bear_text, tool_calls=bear_tools)
        )
        last_bear_text = bear_text

    # Programmatic citation extraction + verification (deterministic, not LLM)
    bull_full_text = "\n\n".join(t.text for t in transcript if t.role == "bull")
    bear_full_text = "\n\n".join(t.text for t in transcript if t.role == "bear")
    bull_cites = extract_citations(bull_full_text)
    bear_cites = extract_citations(bear_full_text)
    bull_verified = verify_citations(bull_cites, bull_pool, company=company)
    bear_verified = verify_citations(bear_cites, bear_pool, company=company)

    # Build a structured manifest for the moderator so it can produce the
    # citation-tracking table (C). The moderator sees the verification results
    # too — but the report we APPEND below is generated by code, not the LLM.
    bull_cite_lines = [f"  {idx + 1}. {vc.citation.raw}" for idx, vc in enumerate(bull_verified)]
    bear_cite_lines = [f"  {idx + 1}. {vc.citation.raw}" for idx, vc in enumerate(bear_verified)]
    bull_dist = source_type_distribution(bull_pool)
    bear_dist = source_type_distribution(bear_pool)
    manifest = (
        "## 자동 추출된 인용 (사회자 참고용)\n\n"
        f"Bull 인용 {len(bull_cites)}건:\n"
        + ("\n".join(bull_cite_lines) if bull_cite_lines else "  (없음)")
        + f"\n\nBear 인용 {len(bear_cites)}건:\n"
        + ("\n".join(bear_cite_lines) if bear_cite_lines else "  (없음)")
        + f"\n\nBull 외부 풀 분포: {bull_dist or '없음'}"
        + f"\n\nBear 외부 풀 분포: {bear_dist or '없음'}"
    )

    full_dialogue = "\n\n".join(
        f"### Round {t.round_idx} - {t.role.upper()}\n{t.text}" for t in transcript
    )
    mod_prompt = (
        f"기업: **{company}** (시장: {market})\n\n"
        f"아래는 Bull과 Bear 애널리스트의 토론 전문입니다. 정해진 형식대로 정리하세요.\n"
        f"특히 **인용 추적 표**(어느 측이 인용한 외부 주장이 상대방에 의해 반박/수용되었는지)를 "
        f"포함해야 합니다.\n\n"
        f"{manifest}\n\n"
        f"---\n{full_dialogue}\n---"
    )
    mod_text, _, _, _ = await _agent_run(
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

    # Programmatic verification report (independent of LLM output)
    verification_md = render_verification_report(
        bull_pool, bear_pool, bull_verified, bear_verified
    )
    transcript.append(
        AgentTurn(
            role="verification",
            round_idx=len(round_kinds) + 2,
            round_kind="verify",
            text=verification_md,
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
