from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol

from .config import Settings


@dataclass
class Transcript:
    text: str
    start: float | None = None
    end: float | None = None


class ASRProvider(Protocol):
    async def transcribe(self, audio: Any, language: str) -> Transcript:
        ...


class DemoASR:
    def __init__(self, settings: Settings) -> None:
        self._sample_rate = settings.sample_rate

    async def transcribe(self, audio: Any, language: str) -> Transcript:
        if hasattr(audio, "size"):
            duration = audio.size / self._sample_rate
        else:
            duration = len(audio) / 4 / self._sample_rate
        if duration <= 0:
            return Transcript(text="")
        label = "Demo transcript" if language == "en" else "演示听写"
        return Transcript(text=f"{label}: received {duration:.1f}s audio")


class FasterWhisperASR:
    def __init__(self, settings: Settings) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "faster-whisper is not installed. Run `pip install -r requirements.txt` "
                "or use the Docker image."
            ) from exc

        self._model = WhisperModel(
            settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
        self._sample_rate = settings.sample_rate

    async def transcribe(self, audio: Any, language: str) -> Transcript:
        return await asyncio.to_thread(self._transcribe_sync, audio, language)

    def _transcribe_sync(self, audio: Any, language: str) -> Transcript:
        segments, _info = self._model.transcribe(
            audio,
            language=language,
            task="transcribe",
            vad_filter=True,
            beam_size=1,
            condition_on_previous_text=False,
            without_timestamps=False,
        )
        parts = list(segments)
        text = " ".join(segment.text.strip() for segment in parts if segment.text.strip()).strip()
        if not text:
            return Transcript(text="")
        start = parts[0].start if parts else None
        end = parts[-1].end if parts else len(audio) / self._sample_rate
        return Transcript(text=text, start=start, end=end)


def create_asr(settings: Settings) -> ASRProvider:
    if settings.asr_provider == "demo":
        return DemoASR(settings)
    return FasterWhisperASR(settings)
