from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class AudioBuffer:
    sample_rate: int
    chunk_seconds: float
    min_audio_seconds: float
    samples: list[bytes] = field(default_factory=list)
    last_flush: float = field(default_factory=time.monotonic)

    def append_float32_bytes(self, payload: bytes) -> None:
        if not payload:
            return
        self.samples.append(payload)

    @property
    def duration(self) -> float:
        return sum(len(part) for part in self.samples) / 4 / self.sample_rate

    def ready(self) -> bool:
        elapsed = time.monotonic() - self.last_flush
        return self.duration >= self.min_audio_seconds and (
            self.duration >= self.chunk_seconds or elapsed >= self.chunk_seconds
        )

    def flush(self):
        if not self.samples:
            return []
        payload = b"".join(self.samples)
        self.samples.clear()
        self.last_flush = time.monotonic()
        try:
            import numpy as np
        except ImportError:
            return payload
        audio = np.frombuffer(payload, dtype=np.float32)
        return np.clip(audio, -1.0, 1.0).astype(np.float32, copy=False)
