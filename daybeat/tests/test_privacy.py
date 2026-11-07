"""합성 오디오로 판정 로직을 검증한다.
- '말소리'는 사인파: 200Hz = 사용자, 400Hz = 다른 사람
- 가짜 VAD는 음량, 가짜 임베더는 주파수로 판별한다 (모델 없이 로직만 테스트)
"""

import json

import numpy as np
import soundfile as sf

from daybeat.privacy import (FRAME, SR, FilterConfig, _mute_mask, filter_recording,
                             frames_to_segments, group_conversations)


def fake_vad(block):
    frames = block[: len(block) // FRAME * FRAME].reshape(-1, FRAME)
    return np.sqrt((frames ** 2).mean(axis=1)) > 0.1


class FakeEmbedder:
    def embed(self, wav):
        spec = np.abs(np.fft.rfft(wav))
        freq = np.argmax(spec) * SR / len(wav)
        return np.array([1.0, 0.0]) if abs(freq - 200) < 50 else np.array([0.0, 1.0])


USER = np.array([1.0, 0.0])


def tone(freq, sec):
    t = np.arange(int(sec * SR)) / SR
    return 0.5 * np.sin(2 * np.pi * freq * t)


def make_day(tmp_path):
    rng = np.random.default_rng(0)
    y = rng.normal(0, 0.01, 100 * SR)  # 생활 소음 (비트 재료)

    def put(start, freq, sec):
        y[int(start * SR): int(start * SR) + int(sec * SR)] += tone(freq, sec)

    # 대화 1 (10~22초): 다른 사람 -> 나 -> 다른 사람  => 참여
    put(10, 400, 4)
    put(15, 200, 4)
    put(19.5, 400, 2.5)
    # 대화 2 (62~70초): 다른 사람들끼리만  => 삭제
    put(62, 400, 3)
    put(66, 400, 4)
    path = tmp_path / "day.wav"
    sf.write(path, y.astype(np.float32), SR)
    return path, y


def test_frames_to_segments_merges_and_drops():
    flags = np.array([1, 1, 0, 1, 1, 0, 0, 0, 0, 0, 1, 0], bool)  # 프레임 0.1초
    segs = frames_to_segments(flags, 0.1, min_speech=0.2, merge_gap=0.15)
    assert segs == [(0.0, 0.5)]  # 짧은 끊김은 합치고, 0.1초짜리 조각은 버린다


def test_group_conversations_splits_on_gap():
    convs = group_conversations([(0, 2), (3, 5), (30, 31)], gap=15)
    assert [(c.start, c.end) for c in convs] == [(0, 5), (30, 31)]


def test_mute_mask_fades_and_is_block_independent():
    whole = _mute_mask(0, 1000, [(100, 300)], fade=20)
    split = np.concatenate([_mute_mask(0, 150, [(100, 300)], 20),
                            _mute_mask(150, 850, [(100, 300)], 20)])
    assert np.allclose(whole, split)
    assert whole[50] == 1 and whole[200] == 0 and 0 < whole[110] < 1


def test_filter_keeps_participated_and_deletes_others(tmp_path):
    path, y = make_day(tmp_path)
    out = tmp_path / "out"
    cfg = FilterConfig(block_seconds=7)  # 블록 경계를 일부러 대화 중간에 걸치게
    report = filter_recording(path, out, FakeEmbedder(), USER, fake_vad, cfg)

    decisions = [c["decision"] for c in report["conversations"]]
    assert decisions == ["kept", "deleted"]
    assert report["conversations"][0]["user_speech_sec"] >= 3

    # 참여한 대화만 파일로 남는다
    files = sorted(p.name for p in (out / "conversations").iterdir())
    assert len(files) == 1 and files[0] in ("conv_000009.flac", "conv_000010.flac")

    # 로그에 삭제된 대화의 파일이 없다
    log = json.loads((out / "privacy_log.json").read_text())
    assert "file" not in log["conversations"][1]

    # ambient: 모든 말소리(내 대화 포함)는 무음, 생활 소음은 그대로
    amb, sr = sf.read(out / "ambient.flac")
    assert sr == SR and len(amb) == len(y)
    for a, b in [(10.5, 21.5), (62.5, 69.5)]:
        assert np.abs(amb[int(a * SR): int(b * SR)]).max() < 1e-3
    np.testing.assert_allclose(amb[: 9 * SR], y[: 9 * SR], atol=1e-3)
    np.testing.assert_allclose(amb[80 * SR:], y[80 * SR:], atol=1e-3)


def test_listening_only_is_deleted(tmp_path):
    """나는 말하지 않고 듣기만 한 대화(짧은 맞장구 포함)는 보수적으로 삭제한다."""
    y = np.zeros(30 * SR)
    y[2 * SR: 8 * SR] += tone(400, 6)
    y[8 * SR: int(8.6 * SR)] += tone(200, 0.6)  # "응" 정도
    y[9 * SR: 14 * SR] += tone(400, 5)
    path = tmp_path / "d.wav"
    sf.write(path, y.astype(np.float32), SR)
    report = filter_recording(path, tmp_path / "o", FakeEmbedder(), USER, fake_vad)
    assert [c["decision"] for c in report["conversations"]] == ["deleted"]
    assert not (tmp_path / "o" / "conversations").exists()


def test_embedder_error_means_delete(tmp_path):
    path, _ = make_day(tmp_path)

    class Broken:
        def embed(self, wav):
            raise RuntimeError("model failed")

    report = filter_recording(path, tmp_path / "o", Broken(), USER, fake_vad)
    assert report["kept"] == 0 and all("error" in c for c in report["conversations"])
