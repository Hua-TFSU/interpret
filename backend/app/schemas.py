from enum import Enum
from pydantic import BaseModel, Field


class Direction(str, Enum):
    en_to_zh = "en-zh"
    zh_to_en = "zh-en"


class SessionConfig(BaseModel):
    direction: Direction = Direction.en_to_zh
    sample_rate: int = Field(default=16000, ge=8000, le=48000)
    terms: dict[str, str] = Field(default_factory=dict)


class SubtitleEvent(BaseModel):
    type: str
    direction: Direction
    source_language: str
    target_language: str
    transcript: str
    translation: str
    is_final: bool = True
    latency_ms: int | None = None


class TranslateRequest(BaseModel):
    direction: Direction = Direction.en_to_zh
    text: str = Field(min_length=1)
    terms: dict[str, str] = Field(default_factory=dict)


class ExtractTermsRequest(BaseModel):
    direction: Direction = Direction.en_to_zh
    text: str = Field(min_length=1)
    existing_terms: dict[str, str] = Field(default_factory=dict)
