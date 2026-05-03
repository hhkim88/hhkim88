"""End-to-end debate runner.

Usage:
    uv run python scripts/debate.py 삼성전자 --market KR --rounds 3 --output samsung.md
    uv run python scripts/debate.py AAPL --market US --rounds 3
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="debate")
    parser.add_argument("company")
    parser.add_argument("--market", choices=["KR", "US"], default="KR")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--model", default=None)
    parser.add_argument("--output", "-o", type=Path, default=None)
    args = parser.parse_args(argv)

    from debate.orchestrator import run_debate, DEFAULT_MODEL
    from debate.transcript import to_markdown

    transcript = run_debate(
        args.company,
        market=args.market,
        rounds=args.rounds,
        model=args.model or DEFAULT_MODEL,
    )
    md = to_markdown(args.company, args.market, transcript)
    if args.output:
        args.output.write_text(md, encoding="utf-8")
        print(f"Wrote debate transcript to {args.output}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
