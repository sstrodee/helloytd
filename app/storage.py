"""Настройки и история скачиваний в JSON-файлах."""

import json
import os
import tempfile
from pathlib import Path

from PySide6.QtCore import QLockFile

from .i18n import LANGUAGES
from .options import AUDIO_CHOICES

DEFAULT_SETTINGS = {
    "language": "auto",
    "out_dir": "",              # пусто — папка «Видео\YouTube»
    "mode": "video",            # "video" | "audio"
    "video_height": None,       # None — лучшее доступное
    "audio_format": "mp3-320",  # "mp3-320" | "mp3-192" | "m4a"
    "subtitles": False,
    "cookies_browser": "firefox",
    "cookies_mode": "auto",     # "auto" — только если YouTube требует вход; "always"; "never"
    "route_mode": "auto",       # "auto" | "direct" | "manual"
    "manual_proxy": "",
}
HISTORY_LIMIT = 200


def load_settings(path):
    stored = _read_json(path, {})
    if not isinstance(stored, dict):
        stored = {}
    settings = dict(DEFAULT_SETTINGS)
    for key, default in DEFAULT_SETTINGS.items():
        value = stored.get(key, default)
        if key == "video_height":
            if type(value) is int and value > 0:
                settings[key] = value
        elif type(value) is type(default) and (not isinstance(value, str) or "\0" not in value):
            settings[key] = value
    for key, choices in {
        "mode": ("video", "audio"), "audio_format": AUDIO_CHOICES,
        "cookies_mode": ("auto", "always", "never"), "route_mode": ("auto", "direct", "manual"),
        "language": LANGUAGES,
    }.items():
        if settings[key] not in choices:
            settings[key] = DEFAULT_SETTINGS[key]
    return settings


def save_settings(path, settings):
    _write_json(path, {key: settings.get(key, default) for key, default in DEFAULT_SETTINGS.items()})


def load_history(path):
    entries = _read_json(path, [])
    if not isinstance(entries, list):
        return []
    return [
        {key: value for key, value in entry.items() if key not in _HISTORY_TEXT or isinstance(value, str)}
        for entry in entries if isinstance(entry, dict)
    ][:HISTORY_LIMIT]


_HISTORY_TEXT = {"title", "path", "kind", "detail", "message", "thumbnail"}


def append_history(path, entry, limit=HISTORY_LIMIT):
    _write_json(path, [entry, *load_history(path)][:limit])


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as file:
            return json.load(file)
    except (OSError, ValueError):
        return default


def _write_json(path, data):
    """Пишет во временный файл и подменяет им старый — обрыв не испортит данные."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as file:
            temporary = Path(file.name)
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def lock_data_dir(folder):
    """Два окна не должны записывать одну историю и обновлять один runtime одновременно."""
    folder.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(folder / "instance.lock"))
    lock.setStaleLockTime(0)
    return lock if lock.tryLock(0) else None


def clear_history(path):
    _write_json(path, [])


def app_data_dir(root, appdata=None):
    """Папка data рядом с программой: portable — удалил папку, и следов нет.

    Если туда писать нельзя (Program Files без прав), — в папку «helloytd» в %APPDATA%.
    """
    folder = Path(root) / "data"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=folder):
            pass
        return folder
    except OSError:
        base = appdata or os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / "helloytd"


def keep_caches_inside(folder, environ):
    """Кэши yt-dlp и Deno — в нашу папку, а не в профиль пользователя."""
    cache = Path(folder) / "cache"
    environ["XDG_CACHE_HOME"] = str(cache)
    environ["DENO_DIR"] = str(cache / "deno")
