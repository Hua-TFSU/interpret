from .schemas import Direction


LANGUAGE_BY_DIRECTION = {
    Direction.en_to_zh: ("en", "zh"),
    Direction.zh_to_en: ("zh", "en"),
}

LANGUAGE_NAME = {
    "en": "English",
    "zh": "Chinese",
}


def languages_for(direction: Direction) -> tuple[str, str]:
    return LANGUAGE_BY_DIRECTION[direction]


def translation_instruction(
    source_language: str,
    target_language: str,
    terms: dict[str, str] | None = None,
) -> str:
    instruction = (
        f"Translate from {LANGUAGE_NAME[source_language]} to {LANGUAGE_NAME[target_language]}. "
        "Return only the translated subtitle text. Keep names, numbers, and technical terms accurate. "
        "Do not add explanations."
    )
    if terms:
        glossary = "; ".join(f"{source} => {target}" for source, target in terms.items())
        instruction += f" Use this glossary exactly when applicable: {glossary}."
    return instruction
