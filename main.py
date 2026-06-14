#!/usr/bin/env python3
"""38.co.kr 공모주 청약 정보 크롤링 & 분석 CLI.

사용 예시
--------
  # 1) 크롤링만 (CSV 저장)
  python main.py crawl --max-pages 20 --out-dir data

  # 2) 저장된 CSV 로 분석
  python main.py analyze --data-dir data --max-competition 200 --min-return 30

  # 3) 크롤링 + 분석 한 번에
  python main.py run --max-pages 20 --out-dir data --max-competition 200

주의: 38.co.kr 외부 접속이 가능한 네트워크 환경에서 실행해야 합니다.
"""

from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

from ipo38 import analyze, crawler


def _save(df: pd.DataFrame, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"  저장: {path} ({len(df)}건)")


def cmd_crawl(args) -> tuple[pd.DataFrame, pd.DataFrame]:
    print("[1/2] 공모주 청약일정 수집...")
    sub = crawler.crawl_subscriptions(max_pages=args.max_pages)
    print(f"  -> 청약 {len(sub)}건")
    print("[2/2] 신규상장 종목(수익률) 수집...")
    ret = crawler.crawl_new_listings(max_pages=args.max_pages)
    print(f"  -> 신규상장 {len(ret)}건")

    _save(sub, os.path.join(args.out_dir, "subscriptions.csv"))
    _save(ret, os.path.join(args.out_dir, "new_listings.csv"))
    return sub, ret


def _load(data_dir: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    sub_p = os.path.join(data_dir, "subscriptions.csv")
    ret_p = os.path.join(data_dir, "new_listings.csv")
    if not (os.path.exists(sub_p) and os.path.exists(ret_p)):
        sys.exit(f"오류: {sub_p} / {ret_p} 가 없습니다. 먼저 'crawl' 을 실행하세요.")
    return pd.read_csv(sub_p), pd.read_csv(ret_p)


def cmd_analyze(args, sub=None, ret=None) -> None:
    if sub is None or ret is None:
        sub, ret = _load(args.data_dir)

    merged = analyze.merge_subscription_returns(sub, ret)
    merged = analyze.add_efficiency_score(merged)
    out_dir = getattr(args, "out_dir", None) or args.data_dir
    _save(merged, os.path.join(out_dir, "merged.csv"))

    print("\n===== 상관관계 분석 =====")
    rep = analyze.correlation_report(merged)
    print(analyze.summarize(rep))

    print("\n===== 청약경쟁률 낮고 + 수익률 높은 종목 (효율순) =====")
    opp = analyze.find_opportunities(
        merged,
        max_competition=args.max_competition,
        min_return=args.min_return,
    )
    if opp.empty:
        print("조건을 만족하는 종목이 없습니다.")
    else:
        cols = [
            c
            for c in [
                "name",
                "subscription_competition",
                "first_day_return",
                "first_day_return_open",
                "first_day_return_close",
                "efficiency",
            ]
            if c in opp.columns
        ]
        with pd.option_context("display.max_rows", 50, "display.width", 200):
            print(opp[cols].head(args.top).to_string(index=False))
        _save(opp, os.path.join(out_dir, "opportunities.csv"))


def cmd_run(args) -> None:
    sub, ret = cmd_crawl(args)
    args.data_dir = args.out_dir
    cmd_analyze(args, sub=sub, ret=ret)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="38.co.kr 공모주 청약 크롤링/분석")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("crawl", help="크롤링 후 CSV 저장")
    c.add_argument("--max-pages", type=int, default=20)
    c.add_argument("--out-dir", default="data")
    c.set_defaults(func=lambda a: cmd_crawl(a))

    a = sub.add_parser("analyze", help="저장된 CSV 분석")
    a.add_argument("--data-dir", default="data")
    a.add_argument("--max-competition", type=float, default=None,
                   help="이 청약경쟁률(:1) 이하만. 미지정 시 하위 50%% 분위 사용")
    a.add_argument("--min-return", type=float, default=0.0,
                   help="최소 첫날 수익률(%%)")
    a.add_argument("--top", type=int, default=30)
    a.set_defaults(func=cmd_analyze)

    r = sub.add_parser("run", help="크롤링 + 분석")
    r.add_argument("--max-pages", type=int, default=20)
    r.add_argument("--out-dir", default="data")
    r.add_argument("--max-competition", type=float, default=None)
    r.add_argument("--min-return", type=float, default=0.0)
    r.add_argument("--top", type=int, default=30)
    r.set_defaults(func=cmd_run)
    return p


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
