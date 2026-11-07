"""사용법
  # 1) 내 목소리 등록 (조용한 곳과 시끄러운 곳에서 각 30초 이상 권장)
  python -m daybeat enroll my_voice_1.m4a my_voice_2.m4a -o me.npy

  # 2) 하루 녹음 필터링
  python -m daybeat filter day.m4a --profile me.npy -o out/ --start 08:00 --delete-input
"""

from __future__ import annotations

import argparse
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np

from .audio_io import ensure_16k_mono
from .privacy import FilterConfig, build_profile, filter_recording, webrtc_vad


def _enroll(args) -> None:
    from .embedder import ResemblyzerEmbedder

    with tempfile.TemporaryDirectory() as tmp:
        paths = [ensure_16k_mono(Path(p), Path(tmp)) for p in args.samples]
        profile = build_profile(paths, ResemblyzerEmbedder(), webrtc_vad(args.vad))
    np.save(args.output, profile)
    print(f"목소리 프로필 저장: {args.output}")


def _filter(args) -> None:
    from .embedder import ResemblyzerEmbedder

    cfg = FilterConfig(
        similarity_threshold=args.threshold,
        min_user_seconds=args.min_user_seconds,
        conversation_gap=args.conversation_gap,
    )
    start = datetime.strptime(args.start, "%H:%M") if args.start else None
    src = Path(args.input)
    with tempfile.TemporaryDirectory() as tmp:
        audio = ensure_16k_mono(src, Path(tmp))  # 변환본은 임시 폴더와 함께 자동 삭제
        report = filter_recording(audio, Path(args.output), ResemblyzerEmbedder(),
                                  np.load(args.profile), webrtc_vad(args.vad), cfg, start)

    print(f"대화 {report['kept'] + report['deleted']}건 중 보관 {report['kept']}건, 삭제 {report['deleted']}건")
    for c in report["conversations"]:
        mark = "보관" if c["decision"] == "kept" else "삭제"
        print(f"  [{mark}] {c['time']}  {c['duration_sec']:>6}s  "
              f"내 발화 {c['user_speech_sec']:>5}s  최대유사도 {c['max_similarity']}")
    if args.delete_input:
        src.unlink()
        print(f"원본 삭제: {src}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="daybeat")
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("enroll", help="내 목소리 프로필 만들기")
    e.add_argument("samples", nargs="+")
    e.add_argument("-o", "--output", default="me.npy")
    e.add_argument("--vad", type=int, default=2, choices=range(4))
    e.set_defaults(fn=_enroll)

    f = sub.add_parser("filter", help="참여하지 않은 대화 삭제")
    f.add_argument("input")
    f.add_argument("--profile", required=True)
    f.add_argument("-o", "--output", default="out")
    f.add_argument("--start", help="녹음 시작 시각 HH:MM (파일 이름과 로그용)")
    f.add_argument("--threshold", type=float, default=0.75, help="내 목소리로 볼 유사도 기준")
    f.add_argument("--min-user-seconds", type=float, default=2.0, help="참여로 볼 최소 발화 시간")
    f.add_argument("--conversation-gap", type=float, default=15.0, help="대화를 나누는 침묵 길이(초)")
    f.add_argument("--vad", type=int, default=2, choices=range(4))
    f.add_argument("--delete-input", action="store_true", help="처리 후 원본 녹음 삭제")
    f.set_defaults(fn=_filter)

    args = p.parse_args(argv)
    args.fn(args)
