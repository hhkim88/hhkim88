"""Aggregate stance-biased external arguments from multiple sources.

The debate orchestrator currently lets each agent generate logic from raw
data. This module exposes a single tool that pulls together the *existing*
arguments circulating in the wild — brokerage notes cited in news, public
analyst PDFs, curated YouTube transcripts, and retail/social posts — so the
Bull and Bear agents can quote and react to real-world commentary instead of
synthesising every claim from scratch.
"""

from __future__ import annotations

from typing import Any

from company_search.sources import (
    news_kr,
    news_us,
    reports,
    secondary,
    social,
    youtube,
)

# Body excerpt size per item — long enough for the agent to extract the actual
# claim, short enough to keep the aggregated payload below the MCP-tool 25k
# limit when ~25 items are returned.
SNIPPET_CHARS = 600


def _is_error_doc(doc: dict[str, Any]) -> bool:
    return "error" in doc and len(doc) <= 2  # source modules sometimes return [{"error": "..."}]


def _make_item(
    source_type: str,
    doc: dict[str, Any],
    *,
    fallback_source_name: str = "",
) -> dict[str, Any]:
    metadata = doc.get("metadata") or {}
    source_name = (
        metadata.get("feed_source")
        or metadata.get("channel")
        or metadata.get("subreddit")
        or metadata.get("platform")
        or metadata.get("broker")
        or fallback_source_name
    )
    body = (doc.get("body_md") or "").strip()
    return {
        "source_type": source_type,
        "title": (doc.get("title") or "").strip(),
        "snippet": body[:SNIPPET_CHARS] + ("..." if len(body) > SNIPPET_CHARS else ""),
        "source_name": str(source_name) if source_name else "",
        "url": doc.get("url") or "",
        "published_at": doc.get("published_at"),
        "broker_keyword": metadata.get("broker_keyword"),  # secondary reports only
        "report_date": metadata.get("report_date"),  # public reports only
    }


def _safe_call(fn, *args, **kwargs) -> list[dict[str, Any]]:
    try:
        out = fn(*args, **kwargs)
    except Exception as exc:
        return [{"error": f"{fn.__module__}.{fn.__name__}: {exc}"}]
    if not isinstance(out, list):
        return []
    return out


def collect_existing_arguments(
    company: str,
    market: str = "KR",
    stance: str = "bull",
    per_source_limit: int = 4,
) -> dict[str, Any]:
    """Aggregate stance-biased external arguments into a uniform structure.

    Args:
        company: Company name (KR) or ticker/name (US).
        market: "KR" or "US".
        stance: "bull" or "bear" — biases news keyword expansion.
        per_source_limit: How many items to pull from each source.

    Returns:
        {
            "company", "market", "stance",
            "items": [ {source_type, title, snippet, source_name, url, ...}, ... ],
            "counts": {source_type: count, ...},
            "errors": [ {source: "...", error: "..."}, ... ],
        }
    """
    if stance not in ("bull", "bear"):
        stance = "bull"

    items: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    # 1. Stance-biased news (the main vehicle for keyword bias)
    news_fn = news_kr.search_news_kr if market == "KR" else news_us.search_news_us
    news_docs = _safe_call(news_fn, company, stance=stance, limit=per_source_limit)
    for doc in news_docs:
        if _is_error_doc(doc):
            errors.append({"source": "news", "error": doc["error"]})
            continue
        items.append(_make_item("news_stance", doc, fallback_source_name="news"))

    # 2. Secondary reports — news articles citing brokerage analyst notes
    sec_docs = _safe_call(secondary.search_secondary, company, market=market, limit=per_source_limit)
    for doc in sec_docs:
        if _is_error_doc(doc):
            errors.append({"source": "secondary", "error": doc["error"]})
            continue
        items.append(_make_item("secondary_report", doc, fallback_source_name="secondary"))

    # 3. Public analyst PDFs (Hankyung Consensus, KR only)
    if market == "KR":
        rep_docs = _safe_call(reports.search_reports, company, limit=per_source_limit)
        for doc in rep_docs:
            if _is_error_doc(doc):
                errors.append({"source": "reports", "error": doc["error"]})
                continue
            items.append(_make_item("public_report", doc, fallback_source_name="hankyung"))

    # 4. Curated investment YouTube channels
    yt_docs = _safe_call(youtube.search_youtube, company, market=market, limit=max(2, per_source_limit - 1))
    for doc in yt_docs:
        if _is_error_doc(doc):
            errors.append({"source": "youtube", "error": doc["error"]})
            continue
        items.append(_make_item("youtube", doc, fallback_source_name="youtube"))

    # 5. Social discussion (Reddit US / Naver KR)
    soc_docs = _safe_call(social.search_social, company, market=market, limit=per_source_limit)
    for doc in soc_docs:
        if _is_error_doc(doc):
            errors.append({"source": "social", "error": doc["error"]})
            continue
        items.append(_make_item("social", doc, fallback_source_name="social"))

    counts: dict[str, int] = {}
    for it in items:
        counts[it["source_type"]] = counts.get(it["source_type"], 0) + 1

    return {
        "company": company,
        "market": market,
        "stance": stance,
        "counts": counts,
        "items": items,
        "errors": errors,
        "note": (
            "각 항목의 'snippet'에는 출처 본문 첫 600자가 들어 있습니다. "
            "토론에서 인용할 때는 [출처: source_name 발행일] 형식으로 표기하세요. "
            "items가 비어있거나 errors가 많으면, 해당 시장에서 데이터 수집이 "
            "제한적이라는 신호이므로 LLM 자체 합성 비중을 높이세요."
        ),
    }
