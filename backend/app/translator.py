from __future__ import annotations

import json
import re
from typing import Protocol

import httpx

from .config import Settings
from .languages import translation_instruction


class Translator(Protocol):
    async def translate(
        self,
        text: str,
        source_language: str,
        target_language: str,
        terms: dict[str, str] | None = None,
    ) -> str:
        ...


class OpenAICompatibleTranslator:
    def __init__(self, settings: Settings, api_key: str | None = None) -> None:
        self._api_key = api_key or settings.openai_api_key
        self._base_url = settings.openai_base_url.rstrip("/")
        self._model = settings.openai_translation_model
        self._timeout = settings.translation_timeout_seconds

    async def translate(
        self,
        text: str,
        source_language: str,
        target_language: str,
        terms: dict[str, str] | None = None,
    ) -> str:
        if not text:
            return ""
        if not self._api_key:
            return await self._translate_with_mymemory(text, source_language, target_language, terms or {})

        payload = {
            "model": self._model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": translation_instruction(source_language, target_language, terms),
                },
                {"role": "user", "content": text},
            ],
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()

    async def _translate_with_mymemory(
        self,
        text: str,
        source_language: str,
        target_language: str,
        terms: dict[str, str],
    ) -> str:
        langpair = f"{self._to_mymemory_language(source_language)}|{self._to_mymemory_language(target_language)}"
        protected_text, placeholders = self._protect_terms(text, terms)
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    "https://api.mymemory.translated.net/get",
                    params={"q": protected_text, "langpair": langpair},
                )
                response.raise_for_status()
                data = json.loads(response.content.decode("utf-8"))
                translated = data.get("responseData", {}).get("translatedText")
                if translated:
                    return self._restore_terms(translated.strip(), placeholders)
        except httpx.HTTPError:
            pass
        return self._restore_terms(protected_text, placeholders)

    @staticmethod
    def _to_mymemory_language(language: str) -> str:
        return {"en": "en-US", "zh": "zh-CN"}.get(language, language)

    @staticmethod
    def _protect_terms(text: str, terms: dict[str, str]) -> tuple[str, dict[str, str]]:
        protected = text
        placeholders: dict[str, str] = {}
        for index, (source, target) in enumerate(terms.items()):
            clean_source = source.strip()
            clean_target = target.strip()
            if not clean_source or not clean_target:
                continue
            if not re.search(re.escape(clean_source), protected, flags=re.IGNORECASE):
                continue
            placeholder = f"HUATFSUTERM{index}"
            protected = re.sub(re.escape(clean_source), placeholder, protected, flags=re.IGNORECASE)
            placeholders[placeholder] = clean_target
        return protected, placeholders

    @staticmethod
    def _restore_terms(text: str, placeholders: dict[str, str]) -> str:
        restored = text
        for placeholder, target in placeholders.items():
            restored = restored.replace(placeholder, target)
            restored = restored.replace(placeholder.lower(), target)
            restored = restored.replace(placeholder.title(), target)
        for target in placeholders.values():
            if target not in restored:
                restored = f"{restored}（{target}）"
        return restored
