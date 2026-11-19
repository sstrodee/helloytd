"""Распознавание ссылок: что подставить из буфера само и как привести ввод в порядок."""

from urllib.parse import parse_qs, urlsplit
import re

YOUTUBE_HOSTS = ("youtube.com", "youtu.be", "youtube-nocookie.com")
_URL_USERINFO = re.compile(r"(://)[^\s/<>]+@", re.IGNORECASE)


def redact_url_credentials(text):
    return _URL_USERINFO.sub(r"\1", text)


def is_youtube_url(text):
    """Одна ли это ссылка на YouTube — такую можно подставить из буфера без спроса."""
    if not text:
        return False
    text = text.strip()
    if not text or any(char.isspace() for char in text):
        return False
    try:
        parts = urlsplit(text)
    except ValueError:
        return False
    if parts.scheme not in ("http", "https"):
        return False
    host = (parts.hostname or "").lower()
    return any(host == known or host.endswith("." + known) for known in YOUTUBE_HOSTS)


def normalize_url(text):
    """Обрезает пробелы и дописывает https:// к «youtu.be/…»."""
    text = (text or "").strip()
    if "://" in text or any(char.isspace() for char in text) or "." not in text.split("/")[0]:
        return text
    return f"https://{text}"


def has_playlist_param(url):
    return "list" in parse_qs(urlsplit(url or "").query)
