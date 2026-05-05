"""End-to-end debate runner.

Usage:
    uv run python scripts/debate.py 삼성전자 --market KR --rounds 3 --output samsung.md
    uv run python scripts/debate.py AAPL --market US --rounds 3
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# On Windows, default subprocess pipe decoding is the system code page (cp949
# in Korean locales), which corrupts UTF-8 output from child processes such as
# yt-dlp. Force UTF-8 mode for all child Python processes.
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from dotenv import load_dotenv

# encoding='utf-8-sig' silently strips a UTF-8 BOM if present. PowerShell's
# `Out-File -Encoding utf8` writes a BOM, which otherwise leaves the first
# variable name like '﻿DART_API_KEY' and os.environ.get('DART_API_KEY')
# returns nothing.
load_dotenv(encoding="utf-8-sig")


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
