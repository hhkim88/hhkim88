"""Debug CLI for individual sources.

Usage:
    uv run python -m company_search news <company> [--stance bull|bear] [--limit N]
    uv run python -m company_search news-us <company> [--stance bull|bear] [--limit N]
    uv run python -m company_search financials <company> [--year YYYY]
    uv run python -m company_search financials-us <ticker>
    uv run python -m company_search price <ticker> [--days N]
    uv run python -m company_search reports <company> [--limit N]
    uv run python -m company_search social <company> [--limit N]
    uv run python -m company_search youtube <company> [--limit N]
    uv run python -m company_search consensus <ticker>
    uv run python -m company_search ir <company> [--limit N]
    uv run python -m company_search resolve <query>
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()


def _print(obj):
    print(json.dumps(obj, default=str, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="company-search")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("news"); p.add_argument("company"); p.add_argument("--stance", default="neutral"); p.add_argument("--limit", type=int, default=5)
    p = sub.add_parser("news-us"); p.add_argument("company"); p.add_argument("--stance", default="neutral"); p.add_argument("--limit", type=int, default=5)
    p = sub.add_parser("financials"); p.add_argument("company"); p.add_argument("--year", type=int, default=datetime.utcnow().year - 1)
    p = sub.add_parser("financials-us"); p.add_argument("ticker")
    p = sub.add_parser("price"); p.add_argument("ticker"); p.add_argument("--days", type=int, default=365)
    p = sub.add_parser("reports"); p.add_argument("company"); p.add_argument("--limit", type=int, default=5)
    p = sub.add_parser("social"); p.add_argument("company"); p.add_argument("--limit", type=int, default=10); p.add_argument("--market", default="US")
    p = sub.add_parser("youtube"); p.add_argument("company"); p.add_argument("--limit", type=int, default=5)
    p = sub.add_parser("consensus"); p.add_argument("company"); p.add_argument("--market", default="KR")
    p = sub.add_parser("ir"); p.add_argument("company"); p.add_argument("--limit", type=int, default=5)
    p = sub.add_parser("resolve"); p.add_argument("query")

    args = parser.parse_args(argv)

    if args.cmd == "resolve":
        from .ticker import resolve

        info = resolve(args.query)
        _print(info.__dict__ if info else None)
        return 0

    if args.cmd == "price":
        from .sources.price import get_price_history

        _print(get_price_history(args.ticker, days=args.days))
        return 0

    if args.cmd == "financials":
        from .sources.financials_kr import get_annual_financials

        _print(get_annual_financials(args.company, year=args.year))
        return 0

    if args.cmd == "financials-us":
        from .sources.financials_us import get_fundamentals

        _print(get_fundamentals(args.ticker))
        return 0

    if args.cmd == "news":
        from .sources.news_kr import search_news_kr

        _print(search_news_kr(args.company, stance=args.stance, limit=args.limit))
        return 0

    if args.cmd == "news-us":
        from .sources.news_us import search_news_us

        _print(search_news_us(args.company, stance=args.stance, limit=args.limit))
        return 0

    if args.cmd == "reports":
        from .sources.reports import search_reports

        _print(search_reports(args.company, limit=args.limit))
        return 0

    if args.cmd == "social":
        from .sources.social import search_social

        _print(search_social(args.company, market=args.market, limit=args.limit))
        return 0

    if args.cmd == "youtube":
        from .sources.youtube import search_youtube

        _print(search_youtube(args.company, limit=args.limit))
        return 0

    if args.cmd == "consensus":
        from .sources.consensus import get_consensus

        _print(get_consensus(args.company, market=args.market))
        return 0

    if args.cmd == "ir":
        from .sources.ir import search_ir

        _print(search_ir(args.company, limit=args.limit))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
