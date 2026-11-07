"""화자 임베딩 모델 래퍼. 기본값은 가볍게 쓸 수 있는 Resemblyzer(GE2E)."""

from __future__ import annotations

import numpy as np


class ResemblyzerEmbedder:
    def __init__(self, device: str | None = None):
        from resemblyzer import VoiceEncoder

        self.encoder = VoiceEncoder(device=device, verbose=False)

    def embed(self, wav: np.ndarray) -> np.ndarray:
        return self.encoder.embed_utterance(wav.astype(np.float32))
