from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Hua-TFSU Real-time Interpreter"
    host: str = "0.0.0.0"
    port: int = 8000

    whisper_model: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    asr_provider: str = "faster_whisper"
    sample_rate: int = 16000
    chunk_seconds: float = 2.4
    min_audio_seconds: float = 0.8

    translation_provider: str = "openai"
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_translation_model: str = "gpt-4o-mini"
    translation_timeout_seconds: float = 20.0

    model_config = SettingsConfigDict(env_file=".env", env_prefix="HUA_TFSU_", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
