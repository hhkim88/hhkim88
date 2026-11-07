"""하루 녹음에서 '내가 참여한 대화'만 남기고, 나머지 대화는 삭제하는 프라이버시 필터.

처리 흐름
1. VAD로 말소리 구간을 찾는다.
2. 침묵 간격(conversation_gap)을 기준으로 말소리 구간을 '대화' 단위로 묶는다.
3. 대화마다 화자 임베딩을 사용자 목소리 프로필과 비교한다.
   사용자가 min_user_seconds 이상 말했으면 '참여한 대화'로 보고 보관한다.
4. 참여하지 않은 대화는 파일로 쓰지 않는다(삭제).
5. 비트 재료(ambient)에서는 모든 대화 구간을 무음 처리한다.

안전 원칙: 판단이 애매하면 삭제한다. 사용자가 듣기만 하고 말하지 않은 대화,
목소리 판정 중 오류가 난 대화도 삭제한다.
하루치 오디오(16kHz 기준 약 5GB float)를 메모리에 올리지 않도록 블록 단위로 처리한다.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable, Protocol

import numpy as np
import soundfile as sf

SR = 16000
FRAME_MS = 30
FRAME = SR * FRAME_MS // 1000  # webrtcvad 프레임 길이(샘플 수)

# float32 블록(길이는 FRAME의 배수)을 받아 프레임별 말소리 여부(bool 배열)를 돌려주는 함수
VadFn = Callable[[np.ndarray], np.ndarray]


class Embedder(Protocol):
    def embed(self, wav: np.ndarray) -> np.ndarray:
        """16kHz mono float32 오디오 -> 화자 임베딩 벡터"""


@dataclass
class FilterConfig:
    block_seconds: float = 600.0       # 스트리밍 처리 블록 길이
    min_speech: float = 0.3            # 이보다 짧은 말소리 조각은 무시
    merge_gap: float = 0.5             # 이보다 짧은 끊김은 같은 발화로 합침
    conversation_gap: float = 15.0     # 이 시간 이상 조용하면 다른 대화로 나눔
    pad: float = 0.3                   # 말소리 앞뒤 여유 구간(무음 처리, 클립 저장 시)
    fade: float = 0.02                 # 무음 처리 경계의 페이드(클릭음 방지)
    window: float = 1.6                # 화자 판정 창 길이
    hop: float = 0.8                   # 화자 판정 창 이동 간격
    min_window: float = 0.5            # 이보다 짧은 발화는 판정에 쓰지 않음
    similarity_threshold: float = 0.75 # 사용자 목소리로 볼 코사인 유사도 기준
    min_user_seconds: float = 2.0      # 사용자가 이만큼 이상 말해야 '참여'


@dataclass
class Conversation:
    start: float
    end: float
    segments: list[tuple[float, float]] = field(default_factory=list)
    speech_seconds: float = 0.0
    user_seconds: float = 0.0
    max_similarity: float = 0.0
    participant: bool = False
    error: str | None = None


# ---------------------------------------------------------------- VAD

def webrtc_vad(aggressiveness: int = 2) -> VadFn:
    import webrtcvad

    vad = webrtcvad.Vad(aggressiveness)

    def fn(block: np.ndarray) -> np.ndarray:
        pcm = (np.clip(block, -1.0, 1.0) * 32767).astype("<i2")
        n = len(pcm) // FRAME
        return np.fromiter(
            (vad.is_speech(pcm[i * FRAME:(i + 1) * FRAME].tobytes(), SR) for i in range(n)),
            dtype=bool, count=n,
        )

    return fn


def frames_to_segments(flags: np.ndarray, frame_sec: float, min_speech: float,
                       merge_gap: float) -> list[tuple[float, float]]:
    """프레임별 말소리 여부 -> (시작, 끝) 초 단위 구간 목록"""
    if not flags.any():
        return []
    padded = np.concatenate([[False], flags, [False]]).astype(np.int8)
    diff = np.diff(padded)
    starts = np.flatnonzero(diff == 1) * frame_sec
    ends = np.flatnonzero(diff == -1) * frame_sec

    merged: list[list[float]] = []
    for s, e in zip(starts, ends):
        if merged and s - merged[-1][1] < merge_gap:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    return [(float(s), float(e)) for s, e in merged if e - s >= min_speech]


def detect_speech(path: Path, vad: VadFn, cfg: FilterConfig) -> list[tuple[float, float]]:
    block = max(FRAME, int(cfg.block_seconds * SR) // FRAME * FRAME)
    flags = []
    for chunk in sf.blocks(str(path), blocksize=block, dtype="float32", fill_value=0.0):
        flags.append(vad(chunk))
    if not flags:
        return []
    return frames_to_segments(np.concatenate(flags), FRAME / SR, cfg.min_speech, cfg.merge_gap)


def group_conversations(segments: list[tuple[float, float]], gap: float) -> list[Conversation]:
    convs: list[Conversation] = []
    for s, e in segments:
        if convs and s - convs[-1].end < gap:
            convs[-1].end = e
            convs[-1].segments.append((s, e))
        else:
            convs.append(Conversation(start=s, end=e, segments=[(s, e)]))
    return convs


# ---------------------------------------------------------------- 화자 판정

def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def _windows(seg: np.ndarray, cfg: FilterConfig) -> Iterable[tuple[np.ndarray, float]]:
    """(창 오디오, 그 창이 대표하는 초) 목록"""
    win, hop = int(cfg.window * SR), int(cfg.hop * SR)
    if len(seg) < cfg.min_window * SR:
        return
    if len(seg) <= win:
        yield seg, len(seg) / SR
        return
    starts = list(range(0, len(seg) - win + 1, hop))
    for i, st in enumerate(starts):
        # 겹치는 창이 같은 시간을 중복으로 세지 않도록, 각 창은 hop만큼 대표한다(마지막 창은 끝까지)
        dur = cfg.hop if i < len(starts) - 1 else (len(seg) - st) / SR
        yield seg[st:st + win], dur


def read_region(path: Path, start: float, end: float) -> np.ndarray:
    info = sf.info(str(path))
    a, b = max(0, int(start * SR)), min(info.frames, int(end * SR))
    data, _ = sf.read(str(path), start=a, stop=b, dtype="float32", always_2d=False)
    return data


def score_conversation(path: Path, conv: Conversation, embedder: Embedder,
                       profile: np.ndarray, cfg: FilterConfig) -> Conversation:
    conv.speech_seconds = sum(e - s for s, e in conv.segments)
    try:
        for s, e in conv.segments:
            audio = read_region(path, s, e)
            for w, dur in _windows(audio, cfg):
                sim = _cosine(embedder.embed(w), profile)
                conv.max_similarity = max(conv.max_similarity, sim)
                if sim >= cfg.similarity_threshold:
                    conv.user_seconds += dur
        conv.participant = conv.user_seconds >= cfg.min_user_seconds
    except Exception as exc:  # 판정 실패 시 삭제 쪽으로
        conv.participant = False
        conv.error = repr(exc)
    return conv


def build_profile(paths: Iterable[Path], embedder: Embedder, vad: VadFn,
                  cfg: FilterConfig | None = None) -> np.ndarray:
    """사용자 목소리 샘플(16kHz mono)들로 평균 임베딩 프로필을 만든다."""
    cfg = cfg or FilterConfig()
    embs = []
    for p in paths:
        for s, e in detect_speech(p, vad, cfg):
            for w, _ in _windows(read_region(p, s, e), cfg):
                v = embedder.embed(w)
                embs.append(v / (np.linalg.norm(v) + 1e-9))
    if not embs:
        raise ValueError("목소리 샘플에서 말소리를 찾지 못했습니다.")
    prof = np.mean(embs, axis=0)
    return prof / np.linalg.norm(prof)


# ---------------------------------------------------------------- 출력

def _mute_mask(b0: int, n: int, intervals: list[tuple[int, int]], fade: int) -> np.ndarray:
    """전체 샘플 위치 [b0, b0+n) 구간의 게인(1=원음, 0=무음). 경계에서 fade 샘플 동안 서서히 줄어든다."""
    gain = np.ones(n, dtype=np.float32)
    t = np.arange(b0, b0 + n)
    for s, e in intervals:
        if e <= b0 or s >= b0 + n:
            continue
        lo, hi = max(s, b0) - b0, min(e, b0 + n) - b0
        tt = t[lo:hi]
        depth = np.minimum(tt - s, e - 1 - tt) / max(fade, 1)
        gain[lo:hi] = np.minimum(gain[lo:hi], 1.0 - np.clip(depth, 0.0, 1.0))
    return gain


def write_ambient(path: Path, out: Path, spans: list[tuple[float, float]],
                  cfg: FilterConfig) -> None:
    """모든 대화 구간(참여 여부 무관)을 지운 '비트 재료' 오디오를 쓴다.
    발화 사이 틈에도 VAD가 놓친 작은 말소리가 있을 수 있어 대화 전체 구간을 무음 처리한다."""
    info = sf.info(str(path))
    pad = int(cfg.pad * SR)
    intervals = [(max(0, int(s * SR) - pad), min(info.frames, int(e * SR) + pad))
                 for s, e in spans]
    block = int(cfg.block_seconds * SR)
    pos, k = 0, 0
    with sf.SoundFile(str(out), "w", samplerate=SR, channels=1, format="FLAC") as f:
        for chunk in sf.blocks(str(path), blocksize=block, dtype="float32"):
            # 이미 지나간 구간은 건너뛰어 블록마다 전체 목록을 훑지 않게 한다
            while k < len(intervals) and intervals[k][1] <= pos:
                k += 1
            active = [iv for iv in intervals[k:] if iv[0] < pos + len(chunk)]
            f.write(chunk * _mute_mask(pos, len(chunk), active, int(cfg.fade * SR)))
            pos += len(chunk)


def _clock(offset: float, start_clock: datetime | None) -> str:
    if start_clock:
        return (start_clock + timedelta(seconds=offset)).strftime("%H%M%S")
    h, rem = divmod(int(offset), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}{m:02d}{s:02d}"


def filter_recording(path: Path, out_dir: Path, embedder: Embedder, profile: np.ndarray,
                     vad: VadFn, cfg: FilterConfig | None = None,
                     start_clock: datetime | None = None) -> dict:
    cfg = cfg or FilterConfig()
    path, out_dir = Path(path), Path(out_dir)
    info = sf.info(str(path))
    if info.samplerate != SR or info.channels != 1:
        raise ValueError(f"16kHz mono 오디오가 필요합니다 (입력: {info.samplerate}Hz, {info.channels}ch)")

    segments = detect_speech(path, vad, cfg)
    convs = [score_conversation(path, c, embedder, profile, cfg)
             for c in group_conversations(segments, cfg.conversation_gap)]

    out_dir.mkdir(parents=True, exist_ok=True)
    write_ambient(path, out_dir / "ambient.flac", [(c.start, c.end) for c in convs], cfg)

    conv_dir = out_dir / "conversations"
    log = []
    for c in convs:
        entry = {
            "time": _clock(c.start, start_clock),
            "duration_sec": round(c.end - c.start, 1),
            "speech_sec": round(c.speech_seconds, 1),
            "user_speech_sec": round(c.user_seconds, 1),
            "max_similarity": round(c.max_similarity, 3),
            "decision": "kept" if c.participant else "deleted",
        }
        if c.error:
            entry["error"] = c.error
        if c.participant:
            conv_dir.mkdir(exist_ok=True)
            name = f"conv_{entry['time']}.flac"
            sf.write(str(conv_dir / name), read_region(path, c.start - cfg.pad, c.end + cfg.pad),
                     SR, format="FLAC")
            entry["file"] = f"conversations/{name}"
        log.append(entry)

    # 로그에는 시간과 판정 수치만 남기고, 삭제된 대화의 내용은 어디에도 저장하지 않는다
    report = {
        "source_seconds": round(info.frames / SR, 1),
        "config": asdict(cfg),
        "conversations": log,
        "kept": sum(c.participant for c in convs),
        "deleted": sum(not c.participant for c in convs),
    }
    (out_dir / "privacy_log.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report
