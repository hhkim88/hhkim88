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

from .personas import (
    BEAR_SYSTEM,
    BULL_SYSTEM,
    MODERATOR_REPORT_PREAMBLE,
    MODERATOR_SCORE_PREAMBLE,
    MODERATOR_SYSTEM,
    ROUND_INSTRUCTIONS,
)
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
# Stage 1 (JSON score extraction) runs on Haiku 4.5 by default because the
# claude_agent_sdk subprocess on Windows consistently times out on Sonnet's
# 10-30s first-token latency for large transcripts (VRT v3/v4 both failed
# all 3 retries at Stage 1). Haiku's first-token latency is 1-3s and its
# streaming behavior is more reliable; its JSON-extraction accuracy is
# adequate for the matrix scoring task. Stage 2 (long markdown report)
# stays on Sonnet for prose quality.
MODERATOR_SCORE_MODEL = os.environ.get(
    "MODERATOR_SCORE_MODEL", "claude-haiku-4-5-20251001"
)
MODERATOR_REPORT_MODEL = os.environ.get("MODERATOR_REPORT_MODEL", MODERATOR_MODEL)
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
    final_text_parts: list[str] = []
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
            has_tool_use = False
            for block in msg.content:
                if isinstance(block, ToolUseBlock):
                    has_tool_use = True
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
            # Only AssistantMessages without tool use are "final-answer-style"
            # turns. For tool agents this is the final turn after all tool calls.
            # For non-tool agents (moderator), every turn qualifies. Sonnet 4.6
            # may split long responses across multiple such messages, so we
            # accumulate them in order rather than overwriting.
            if text_parts and not has_tool_use:
                final_text_parts.append("".join(text_parts))
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

    # AssistantMessage TextBlocks (without tool use) contain the model's
    # final-answer text. Concatenate across messages because Sonnet 4.6 splits
    # long outputs into multiple AssistantMessages — capturing only the last
    # one drops earlier sections (observed: DIS moderator missing sections 1-3).
    if final_text_parts:
        final_text = "\n".join(final_text_parts)

    for entry in tool_log:
        if entry["ok"] is None:
            entry["ok"] = False

    return final_text, new_session, tool_log, collect_items


async def _agent_run_with_retry(
    system: str,
    user_msg: str,
    resume_session: str | None,
    model: str,
    use_tools: bool = True,
    attempts: int = 3,
    timeout_s: float = 300.0,
) -> tuple[str, str | None, list[dict[str, Any]], list[dict[str, Any]]]:
    """Run an agent turn, retrying on transient subprocess/API failures.

    The moderator call is the single largest request (full transcript in,
    full structured report out) and the most prone to transient overload/
    network errors. Without retry, one moderator failure discards every
    completed Bull/Bear round. Backoff: 2s, 4s.

    Each attempt is wrapped in a per-call timeout because on Windows the
    claude_agent_sdk subprocess can fail internally ("Fatal error in
    message reader") without closing its anyio stream — leaving the
    receive_event.wait() blocked forever. The plain try/except above
    can't catch that hang; a timeout converts it into a retriable
    TimeoutError so the loop actually runs.
    """
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            with anyio.fail_after(timeout_s):
                return await _agent_run(
                    system, user_msg, resume_session, model, use_tools
                )
        except Exception as exc:  # noqa: BLE001 — transient CLI/API errors + TimeoutError
            last_exc = exc
            if i < attempts - 1:
                await anyio.sleep(2 * (2 ** i))
    assert last_exc is not None
    raise last_exc


async def _anthropic_direct_call(
    system: str,
    user_msg: str,
    model: str,
    max_tokens: int,
    timeout_s: float,
) -> str:
    """Call Claude via the Anthropic HTTP API directly, bypassing the
    claude_agent_sdk subprocess entirely.

    Why: claude_agent_sdk launches the Claude Code CLI as a child process
    and pipes prompts via stdin. On Windows, large inputs (~100K+ chars,
    typical for moderator: 20K system + 80-100K transcript+manifest) hit
    pipe buffer / streaming limits and consistently crash with "Fatal
    error in message reader" regardless of model (Sonnet, Haiku — both
    fail). The HTTP API has no subprocess intermediary, handles arbitrary
    input sizes, and is the canonical path for non-tool-using calls.

    Used by the moderator (use_tools=False). Bull/Bear personas still go
    through claude_agent_sdk because they need tool dispatch
    (collect_existing_arguments, get_financials, etc.).
    """
    import anthropic  # local import — only required for moderator path

    client = anthropic.AsyncAnthropic()
    with anyio.fail_after(timeout_s):
        message = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
    parts: list[str] = []
    for block in message.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    out = "".join(parts).strip()
    if not out:
        raise RuntimeError(
            "Anthropic API returned empty content "
            f"(stop_reason={getattr(message, 'stop_reason', '?')})"
        )
    return out


async def _moderator_call_with_retry(
    system: str,
    user_msg: str,
    model: str,
    max_tokens: int,
    attempts: int = 3,
    timeout_s: float = 300.0,
) -> str:
    """Retry wrapper around _anthropic_direct_call mirroring the
    _agent_run_with_retry pattern (3 attempts, 2/4/8s backoff,
    per-attempt timeout)."""
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            return await _anthropic_direct_call(
                system, user_msg, model, max_tokens=max_tokens, timeout_s=timeout_s
            )
        except Exception as exc:  # noqa: BLE001 — transient API/network errors
            last_exc = exc
            if i < attempts - 1:
                await anyio.sleep(2 * (2 ** i))
    assert last_exc is not None
    raise last_exc


def _parse_score_json(raw: str) -> dict[str, Any]:
    """Pull Stage-1 JSON object out of the moderator's response.

    The Stage-1 prompt asks for a single JSON object inside a ```json code
    fence, but Sonnet sometimes adds a leading sentence or omits the fence.
    Be tolerant: try the fence first, fall back to the outermost {...}.
    Raises ValueError if no parseable object is found — the orchestrator
    treats that as a Stage-1 failure and emits the placeholder.
    """
    text = raw.strip()
    fence_start = text.find("```json")
    if fence_start != -1:
        body_start = text.find("\n", fence_start) + 1
        fence_end = text.find("```", body_start)
        if fence_end != -1:
            return json.loads(text[body_start:fence_end].strip())

    # Fallback: greedy outermost braces.
    first = text.find("{")
    last = text.rfind("}")
    if first == -1 or last == -1 or last < first:
        raise ValueError("no JSON object found in Stage 1 output")
    return json.loads(text[first : last + 1])


def _render_minimal_report_from_score(
    score: dict[str, Any], stage2_error: str
) -> str:
    """Synthesize a minimal markdown report from Stage 1 JSON when Stage 2
    fails. The user still gets the matrix, classification, recommendation,
    and debate-winner verdict — the qualitative sections (2-1 through 2-6)
    are missing but the actionable scoring is preserved.

    This is a fallback path; the full reporter (Stage 2 LLM) writes the
    proper output when it succeeds.
    """
    cls = score.get("classification", {})
    matrix = score.get("matrix", {})
    cur = score.get("current_price", {})
    debate = score.get("debate_winner", {})
    scen = score.get("scenarios", {})
    risk = score.get("risk", {})
    sig = score.get("signals", {})

    def _safe(v: Any, default: str = "—") -> str:
        return str(v) if v not in (None, "") else default

    lines: list[str] = []
    lines.append(
        "> ⚠️ **Stage 2 보고서 작성 실패** — Stage 1 점수는 정상 산출됨. "
        f"오류: {stage2_error}\n"
        "> 이하는 Stage 1 JSON에서 자동 생성된 미니멀 보고서입니다. "
        "전체 마크다운 본문(2-1 합의된 사실 ~ 2-6 핵심 질문)이 누락됐으니 "
        "동일 명령으로 재실행하면 Stage 2만 다시 시도합니다.\n"
    )
    lines.append("## 🎯 TL;DR\n")
    lines.append("| 항목 | 값 |")
    lines.append("|---|---|")
    lines.append(f"| **종목 분류** | {_safe(cls.get('label'))} |")
    lines.append(f"| **종합 권고** | **{_safe(score.get('recommendation'))}** |")
    lines.append(f"| **G (낙관−비관)** | **{_safe(matrix.get('final_g'))}pp** |")
    lines.append(
        f"| **현재가 평가** | {_safe(cur.get('label'))} "
        f"({_safe(cur.get('value'))}) |"
    )
    lines.append(f"| **핵심 강세** | {_safe(score.get('headline_bull'))} |")
    lines.append(f"| **핵심 약세** | {_safe(score.get('headline_bear'))} |")
    lines.append(f"| **결정 트리거** | {_safe(score.get('decision_trigger'))} |")
    lines.append(
        f"| **디베이트 우위** | **{_safe(debate.get('verdict'))}** — "
        f"{_safe(debate.get('reason'))} |"
    )
    if score.get("imbalance_flag"):
        lines.append(f"\n> {score['imbalance_flag']}")
    if score.get("citation_warning"):
        lines.append(f"\n> {score['citation_warning']}")

    lines.append("\n## 📊 매트릭스 (C-1)\n")
    lines.append("| 요인 | 근거 | 비관 ±pp | 낙관 ±pp |")
    lines.append("|---|---|---:|---:|")
    for row in matrix.get("rows", []):
        lines.append(
            f"| {_safe(row.get('factor'))} | {_safe(row.get('evidence'))} | "
            f"{_safe(row.get('pessimism'))} | {_safe(row.get('optimism'))} |"
        )
    cap = matrix.get("cap_check", {}) or {}
    cap_note = (
        f"Bull ❌무시 {cap.get('bull_ignored_bear_core_count', 0)}건 / "
        f"Bear ❌무시 {cap.get('bear_ignored_bull_core_count', 0)}건 → "
        f"적용 캡: {_safe(cap.get('applied_cap'))}"
    )
    lines.append(
        f"\n**소계**: 비관 {_safe(matrix.get('subtotal_pessimism'))} / "
        f"낙관 {_safe(matrix.get('subtotal_optimism'))}\n"
        f"**정규화 후**: 비관 {_safe(matrix.get('final_pessimism_pct'))}% / "
        f"낙관 {_safe(matrix.get('final_optimism_pct'))}% / "
        f"기본 {_safe(matrix.get('final_base_pct'))}%\n"
        f"**원시 G**: {_safe(matrix.get('raw_g'))}pp · "
        f"**G 캡**: {cap_note} · **최종 G**: **{_safe(matrix.get('final_g'))}pp**"
    )

    lines.append("\n## 📅 6개월 시나리오\n")
    lines.append("| 시나리오 | 목표가 | 확률 | 인용 출처 | 트리거 |")
    lines.append("|---|---|---|---|---|")
    for label, key in (("비관", "bearish"), ("기본", "base"), ("낙관", "bullish")):
        s = scen.get(key, {}) or {}
        lines.append(
            f"| {label} | {_safe(s.get('target'))} | "
            f"{_safe(s.get('probability_pct'))}% | "
            f"{_safe(s.get('citation'))} | {_safe(s.get('trigger'))} |"
        )

    lines.append("\n## ⚠️ 리스크 관리\n")
    lines.append(f"- **손절 검토선**: {_safe(risk.get('stop_loss'))}")
    lines.append(f"- **추가 매수 지점**: {_safe(risk.get('add_buy'))}")
    lines.append(
        f"- **단일 종목 비중 한도**: {_safe(risk.get('position_cap_pct'))}%"
    )

    buys = sig.get("buy_triggers") or []
    avoids = sig.get("avoid_triggers") or []
    if buys or avoids:
        lines.append("\n## 🚦 진입 / 회피 시그널\n")
        if buys:
            lines.append("✅ **매수 진입 권고 신호**:")
            for s in buys:
                lines.append(f"- {s}")
        if avoids:
            lines.append("\n❌ **즉시 매수 회피 신호**:")
            for s in avoids:
                lines.append(f"- {s}")

    lines.append(
        "\n---\n*Stage 2 LLM 출력 실패로 인용 추적 표·약점 분석 등 "
        "정성 섹션은 누락됨. Bull/Bear 토론 전문은 아래에 그대로 보존됨.*"
    )
    return "\n".join(lines)


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
                _agent_run_with_retry(BULL_SYSTEM, bull_prompt, bull_session, model),
                _agent_run_with_retry(BEAR_SYSTEM, bear_prompt, bear_session, model),
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
        bull_text, bull_session, bull_tools, bull_round_items = await _agent_run_with_retry(
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
        bear_text, bear_session, bear_tools, bear_round_items = await _agent_run_with_retry(
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

    def _verif_summary(verified: list) -> str:
        v = sum(1 for x in verified if x.status == "verified")
        p = sum(1 for x in verified if x.status == "partial")
        s = sum(1 for x in verified if x.status == "suspect")
        denom = v + p + s
        rate = (v + p) / denom if denom else 1.0
        flag = "  ⚠️ 60% 미만 — 검증율 경고 적용" if rate < 0.60 else ""
        return f"검증율 {rate:.0%} (✅{v} ⚠️{p} ❌{s}, internal 제외){flag}"

    manifest = (
        "## 자동 추출된 인용 (사회자 참고용)\n\n"
        f"Bull 인용 {len(bull_cites)}건:\n"
        + ("\n".join(bull_cite_lines) if bull_cite_lines else "  (없음)")
        + f"\n\nBear 인용 {len(bear_cites)}건:\n"
        + ("\n".join(bear_cite_lines) if bear_cite_lines else "  (없음)")
        + f"\n\nBull 외부 인용 {_verif_summary(bull_verified)}"
        + f"\nBear 외부 인용 {_verif_summary(bear_verified)}"
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
    # Two-stage moderator: Stage 1 emits a compact JSON of scores/decisions
    # (~3K output tokens, very reliable), Stage 2 writes the long markdown
    # report against that JSON as ground truth (~10K output tokens, less
    # computation since decisions are settled). Single-shot output was 15K+
    # tokens and the SDK consistently hung mid-stream on Windows for large
    # transcripts (VRT, SK하이닉스, 현대차 v4). Splitting halves each call's
    # output and gives us a fallback path: if Stage 2 fails, the orchestrator
    # synthesizes a minimal markdown from Stage 1's JSON so the user still
    # gets the matrix and recommendation.
    score_system = MODERATOR_SCORE_PREAMBLE + "\n\n" + MODERATOR_SYSTEM
    report_system = MODERATOR_REPORT_PREAMBLE + "\n\n" + MODERATOR_SYSTEM
    score_json: dict[str, Any] | None = None
    mod_text: str | None = None

    try:
        # Moderator routed via direct Anthropic HTTP API to avoid the
        # Windows-side claude_agent_sdk subprocess pipe failures that
        # killed VRT/SK하이닉스/ETN moderation on every retry.
        score_text = await _moderator_call_with_retry(
            score_system, mod_prompt, MODERATOR_SCORE_MODEL, max_tokens=4000
        )
        score_json = _parse_score_json(score_text)
    except Exception as exc:  # noqa: BLE001 — stage-1 transient failure
        mod_text = (
            "> ⚠️ **사회자 종합 생성 실패** (Stage 1 점수 산출, 3회 재시도 후 오류): "
            f"{str(exc)[:300]}\n\n"
            "> Bull/Bear 토론 전문은 아래에 그대로 보존되어 있습니다. "
            "잠시 후 동일 명령으로 재실행하면 캐시된 검색 결과를 재사용하므로 "
            "검색 비용 없이 토론·종합이 다시 생성됩니다."
        )

    if mod_text is None and score_json is not None:
        # Stage 1 succeeded — try Stage 2 to write the long report. If Stage 2
        # fails, we still have the JSON to fall back on.
        report_prompt = (
            f"기업: **{company}** (시장: {market})\n\n"
            "아래는 Stage 1에서 산출한 매트릭스·분류·시나리오 JSON입니다. "
            "이를 ground truth로 받아 마크다운 보고서를 작성하세요 "
            "(점수 재계산 금지, JSON 값 그대로 인용).\n\n"
            "## Stage 1 JSON (ground truth)\n"
            "```json\n"
            f"{json.dumps(score_json, ensure_ascii=False, indent=2)}\n"
            "```\n\n"
            f"{manifest}\n\n"
            f"---\n{full_dialogue}\n---"
        )
        try:
            mod_text = await _moderator_call_with_retry(
                report_system, report_prompt, MODERATOR_REPORT_MODEL, max_tokens=16000
            )
        except Exception as exc:  # noqa: BLE001 — stage-2 transient failure
            mod_text = _render_minimal_report_from_score(score_json, str(exc)[:300])
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
