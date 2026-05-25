from backend.app.languages import languages_for, translation_instruction
from backend.app.schemas import Direction


def test_language_direction_mapping():
    assert languages_for(Direction.en_to_zh) == ("en", "zh")
    assert languages_for(Direction.zh_to_en) == ("zh", "en")


def test_translation_instruction_mentions_languages():
    instruction = translation_instruction("en", "zh")
    assert "English" in instruction
    assert "Chinese" in instruction
