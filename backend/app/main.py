from __future__ import annotations

import json
import re
import time
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .asr import create_asr
from .audio import AudioBuffer
from .config import get_settings
from .languages import languages_for
from .schemas import Direction, ExtractTermsRequest, SessionConfig, SubtitleEvent, TranslateRequest
from .translator import OpenAICompatibleTranslator

settings = get_settings()
app = FastAPI(title=settings.app_name)

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"

app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/translate")
async def translate_text(
    request: TranslateRequest,
    x_openai_api_key: str | None = Header(default=None),
) -> dict[str, str]:
    source_language, target_language = languages_for(request.direction)
    translator = OpenAICompatibleTranslator(settings, api_key=x_openai_api_key)
    started_at = time.perf_counter()
    try:
        translation = await translator.translate(
            request.text,
            source_language,
            target_language,
            terms=request.terms,
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=f"OpenAI translation request failed: {exc.response.text}",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"OpenAI translation service is not reachable: {exc}",
        ) from exc
    return {
        "type": "translation",
        "direction": request.direction,
        "source_language": source_language,
        "target_language": target_language,
        "transcript": request.text,
        "translation": translation,
        "latency_ms": str(int((time.perf_counter() - started_at) * 1000)),
    }


@app.post("/api/extract-terms")
async def extract_terms(
    request: ExtractTermsRequest,
    x_openai_api_key: str | None = Header(default=None),
) -> dict[str, dict[str, str]]:
    source_language, target_language = languages_for(request.direction)
    if x_openai_api_key:
        prompt = (
            "Extract domain terminology from the input for a bilingual live-caption glossary. "
            f"The source language is {source_language} and target language is {target_language}. "
            "Return only a JSON object mapping source terms to concise preferred translations. "
            "Exclude ordinary words and keep no more than 12 entries."
        )
        payload = {
            "model": settings.openai_translation_model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": request.text},
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=settings.translation_timeout_seconds) as client:
                response = await client.post(
                    f"{settings.openai_base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {x_openai_api_key}"},
                    json=payload,
                )
                response.raise_for_status()
                result = json.loads(response.json()["choices"][0]["message"]["content"])
                terms = {
                    str(source).strip(): str(target).strip()
                    for source, target in result.items()
                    if str(source).strip() and str(target).strip()
                }
                return {"terms": {**request.existing_terms, **terms}}
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError):
            pass

    terms = _extract_terms_fallback(request.text, request.direction)
    return {"terms": {**request.existing_terms, **terms}}


def _extract_terms_fallback(text: str, direction: Direction) -> dict[str, str]:
    if direction == Direction.en_to_zh:
        candidates = re.findall(r"\b(?:[A-Z][A-Za-z0-9-]{2,}(?:\s+[A-Z][A-Za-z0-9-]{2,})*|[A-Z]{2,})\b", text)
        return {term: term for term in dict.fromkeys(candidates[:12])}
    candidates = re.findall(r"[\u4e00-\u9fff]{3,10}", text)
    return {term: term for term in dict.fromkeys(candidates[:12])}


@app.websocket("/ws/subtitle")
async def subtitle_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    config = SessionConfig.model_validate(await websocket.receive_json())
    source_language, target_language = languages_for(config.direction)

    asr = create_asr(settings)
    translator = OpenAICompatibleTranslator(settings)
    buffer = AudioBuffer(
        sample_rate=config.sample_rate,
        chunk_seconds=settings.chunk_seconds,
        min_audio_seconds=settings.min_audio_seconds,
    )

    await websocket.send_json(
        {
            "type": "ready",
            "direction": config.direction,
            "source_language": source_language,
            "target_language": target_language,
        }
    )

    try:
        while True:
            message = await websocket.receive()
            if "bytes" in message:
                buffer.append_float32_bytes(message["bytes"])
                if buffer.ready():
                    await _process_buffer(websocket, buffer, asr, translator, config.direction, config.terms)
            elif message.get("text") == "flush":
                await _process_buffer(websocket, buffer, asr, translator, config.direction, config.terms)
            elif message.get("text") == "stop":
                await _process_buffer(websocket, buffer, asr, translator, config.direction, config.terms)
                await websocket.close()
                return
    except WebSocketDisconnect:
        return


async def _process_buffer(
    websocket: WebSocket,
    buffer,
    asr,
    translator,
    direction: Direction,
    terms: dict[str, str] | None = None,
) -> None:
    audio = buffer.flush()
    if len(audio) == 0:
        return

    started_at = time.perf_counter()
    source_language, target_language = languages_for(direction)
    transcript = await asr.transcribe(audio, source_language)
    if not transcript.text:
        return

    translation = await translator.translate(transcript.text, source_language, target_language, terms=terms)
    latency_ms = int((time.perf_counter() - started_at) * 1000)
    event = SubtitleEvent(
        type="subtitle",
        direction=direction,
        source_language=source_language,
        target_language=target_language,
        transcript=transcript.text,
        translation=translation,
        is_final=True,
        latency_ms=latency_ms,
    )
    await websocket.send_json(event.model_dump(mode="json"))
