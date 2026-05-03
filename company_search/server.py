"""MCP server exposing company-search tools.

Run via Claude Code .mcp.json:
  {
    "mcpServers": {
      "company-search": {
        "command": "uv",
        "args": ["run", "--directory", "/home/user/hhkim88",
                 "python", "-m", "company_search.server"]
      }
    }
  }
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from . import sentiment
from .sources import (
    consensus,
    financials_kr,
    financials_us,
    ir,
    news_kr,
    news_us,
    price,
    reports,
    secondary,
    social,
    youtube,
)
from .ticker import resolve

load_dotenv()

mcp = FastMCP("company-search")


def _json(obj: Any) -> str:
    return json.dumps(obj, default=str, ensure_ascii=False, indent=2)


@mcp.tool()
def search_company_news(company: str, market: str = "KR", stance: str = "neutral", limit: int = 5) -> str:
    """Search recent news articles. stance='bull'|'bear'|'neutral' biases keywords."""
    fn = news_kr.search_news_kr if market == "KR" else news_us.search_news_us
    return _json(sentiment.attach(fn(company, stance=stance, limit=limit)))


@mcp.tool()
def get_financials(company: str, market: str = "KR", year: int | None = None) -> str:
    """Annual financial summary. KR uses OpenDART, US uses yfinance."""
    if market == "KR":
        return _json(financials_kr.get_annual_financials(company, year=year or datetime.utcnow().year - 1))
    return _json(financials_us.get_fundamentals(company))


@mcp.tool()
def get_price_history(ticker: str, days: int = 365) -> str:
    """Daily OHLCV with summary (52w high/low, % change)."""
    return _json(price.get_price_history(ticker, days=days))


@mcp.tool()
def get_analyst_consensus(ticker: str, market: str = "KR") -> str:
    """Target price + recommendation distribution."""
    return _json(consensus.get_consensus(ticker, market=market))


@mcp.tool()
def get_secondary_reports(company: str, market: str = "KR", limit: int = 5) -> str:
    """News articles summarizing brokerage reports."""
    return _json(secondary.search_secondary(company, market=market, limit=limit))


@mcp.tool()
def get_youtube_analysis(company: str, market: str = "KR", limit: int = 3) -> str:
    """Investment YouTube channel transcripts."""
    return _json(youtube.search_youtube(company, market=market, limit=limit))


@mcp.tool()
def get_social_buzz(company: str, market: str = "US", limit: int = 10) -> str:
    """Reddit (US) or Naver discussion board (KR)."""
    return _json(social.search_social(company, market=market, limit=limit))


@mcp.tool()
def get_ir_materials(company: str, market: str = "KR", limit: int = 5) -> str:
    """Company IR filings (KR DART or US SEC 8-K)."""
    return _json(ir.search_ir(company, market=market, limit=limit))


@mcp.tool()
def get_public_reports(company: str, limit: int = 5) -> str:
    """Hankyung Consensus public PDFs (KR only)."""
    return _json(reports.search_reports(company, limit=limit))


@mcp.tool()
def resolve_ticker(query: str, market: str | None = None) -> str:
    """Resolve a company name or ticker to (ticker, name, market)."""
    info = resolve(query, market=market)
    return _json(info.__dict__ if info else None)


if __name__ == "__main__":
    mcp.run()
