"""Anthropic tool-use schemas wrapping company_search functions."""

from __future__ import annotations

from typing import Any

from company_search.sources import (
    consensus,
    earnings_call,
    financials_kr,
    financials_us,
    ir,
    news_kr,
    news_us,
    price,
    reports,
    secondary,
    seekingalpha,
    social,
    youtube,
)
from company_search import sentiment

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "search_company_news",
        "description": "Search recent news articles about a company. Body text included. Use stance='bull' or 'bear' to bias keyword expansion toward positive/negative coverage.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company": {"type": "string"},
                "market": {"type": "string", "enum": ["KR", "US"]},
                "stance": {"type": "string", "enum": ["bull", "bear", "neutral"]},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["company", "market"],
        },
    },
    {
        "name": "get_financials",
        "description": "Get most recent annual financial summary (revenue, operating income, net income, assets, equity).",
        "input_schema": {
            "type": "object",
            "properties": {
                "company": {"type": "string"},
                "market": {"type": "string", "enum": ["KR", "US"]},
                "year": {"type": "integer", "description": "KR only. Defaults to last year."},
            },
            "required": ["company", "market"],
        },
    },
    {
        "name": "get_price_history",
        "description": "Daily OHLCV history for a ticker. Includes summary (52w high/low, % change).",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "days": {"type": "integer", "default": 365},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_analyst_consensus",
        "description": "Analyst consensus: target price distribution, recommendation breakdown.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "market": {"type": "string", "enum": ["KR", "US"]},
            },
            "required": ["ticker", "market"],
        },
    },
    {
        "name": "get_secondary_reports",
        "description": "Second-hand citations: news articles summarizing brokerage analyst reports.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company": {"type": "string"},
                "market": {"type": "string", "enum": ["KR", "US"]},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["company", "market"],
        },
    },
    {
        "name": "get_youtube_analysis",
        "description": "Curated investment YouTube channel transcripts (Korean: 슈카·삼프로TV 등; English: Damodaran 등).",
        "input_schema": {
            "type": "object",
            "properties": {
                "company": {"type": "string"},
                "market": {"type": "string", "enum": ["KR", "US"]},
                "limit": {"type": "integer", "default": 3},
            },
            "required": ["company", "market"],
        },
    },
    {
        "name": "get_social_buzz",
        "description": "Reddit (US) or Naver discussion board (KR) posts about the company.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company": {"type": "string"},
                "market": {"type": "string", "enum": ["KR", "US"]},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["company", "market"],
        },
    },
    {
        "name": "get_ir_materials",
        "description": "Company IR filings (KR: DART quarterly/annual reports; US: SEC 8-K filings).",
        "input_schema": {
            "type": "object",
            "properties": {
                "company": {"type": "string"},
                "market": {"type": "string", "enum": ["KR", "US"]},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["company", "market"],
        },
    },
    {
        "name": "get_public_reports",
        "description": "Hankyung Consensus public analyst PDFs (KR only).",
        "input_schema": {
            "type": "object",
            "properties": {
                "company": {"type": "string"},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["company"],
        },
    },
    {
        "name": "get_earnings_calls",
        "description": "Free earnings call transcripts (US only — Motley Fool). Body text is the actual CEO/CFO Q&A. KR is unsupported (no free Korean equivalent).",
        "input_schema": {
            "type": "object",
            "properties": {
                "company": {"type": "string"},
                "market": {"type": "string", "enum": ["KR", "US"]},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["company", "market"],
        },
    },
    {
        "name": "get_seeking_alpha",
        "description": "Seeking Alpha contributor commentary headlines + Google News snippets (US only). stance='bull'|'bear'|'neutral' biases the article filter.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company": {"type": "string"},
                "stance": {"type": "string", "enum": ["bull", "bear", "neutral"]},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["company"],
        },
    },
]


def dispatch(name: str, args: dict[str, Any]) -> Any:
    """Execute a tool call by name. Returns JSON-serializable result."""
    if name == "search_company_news":
        market = args.get("market", "KR")
        fn = news_kr.search_news_kr if market == "KR" else news_us.search_news_us
        out = fn(
            args["company"],
            stance=args.get("stance", "neutral"),
            limit=args.get("limit", 5),
        )
        return sentiment.attach(out)

    if name == "get_financials":
        market = args.get("market", "KR")
        if market == "KR":
            from datetime import datetime as _dt

            return financials_kr.get_annual_financials(
                args["company"], year=args.get("year", _dt.utcnow().year - 1)
            )
        return financials_us.get_fundamentals(args["company"])

    if name == "get_price_history":
        return price.get_price_history(args["ticker"], days=args.get("days", 365))

    if name == "get_analyst_consensus":
        return consensus.get_consensus(args["ticker"], market=args.get("market", "KR"))

    if name == "get_secondary_reports":
        return secondary.search_secondary(
            args["company"], market=args.get("market", "KR"), limit=args.get("limit", 5)
        )

    if name == "get_youtube_analysis":
        return youtube.search_youtube(
            args["company"], market=args.get("market", "KR"), limit=args.get("limit", 3)
        )

    if name == "get_social_buzz":
        return social.search_social(
            args["company"], market=args.get("market", "KR"), limit=args.get("limit", 10)
        )

    if name == "get_ir_materials":
        return ir.search_ir(
            args["company"], market=args.get("market", "KR"), limit=args.get("limit", 5)
        )

    if name == "get_public_reports":
        return reports.search_reports(args["company"], limit=args.get("limit", 5))

    if name == "get_earnings_calls":
        return earnings_call.search_earnings_calls(
            args["company"], market=args.get("market", "US"), limit=args.get("limit", 5)
        )

    if name == "get_seeking_alpha":
        return seekingalpha.search_seeking_alpha(
            args["company"], stance=args.get("stance", "neutral"), limit=args.get("limit", 5)
        )

    return {"error": f"unknown tool: {name}"}
