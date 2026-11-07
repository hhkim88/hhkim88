"""입력 오디오(m4a, mp3, wav 등)를 16kHz mono FLAC으로 맞춘다."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import soundfile as sf

from .privacy import SR


def ensure_16k_mono(path: Path, work_dir: Path) -> Path:
    path = Path(path)
    try:
        info = sf.info(str(path))
        if info.samplerate == SR and info.channels == 1:
            return path
    except RuntimeError:
        pass  # m4a처럼 soundfile이 못 읽는 형식은 ffmpeg로 변환

    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg가 필요합니다: 16kHz mono 형식이 아닌 입력을 변환해야 합니다.")
    work_dir.mkdir(parents=True, exist_ok=True)
    out = work_dir / f"{path.stem}.16k.flac"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), str(out)],
        check=True,
    )
    return out
