"""Language selection and translation of user-facing text."""

from .translations_en import ENGLISH

LANGUAGES = ("auto", "en", "ru")
_language = "ru"


def resolve_language(preference, ui_languages):
    if preference in ("en", "ru"):
        return preference
    for name in ui_languages:
        language = name.replace("_", "-").split("-")[0].lower()
        if language in ("en", "ru"):
            return language
    return "en"


def set_language(language):
    global _language
    if language not in ("en", "ru"):
        raise ValueError(f"Unsupported UI language: {language}")
    _language = language


def language():
    return _language


def tr(source, **values):
    message = ENGLISH.get(source, source) if _language == "en" else source
    return message.format(**values) if values else message


def video_noun(count):
    if _language == "en":
        return "video" if count == 1 else "videos"
    return "видео"


def video_count(count):
    return f"{count} {video_noun(count)}"
