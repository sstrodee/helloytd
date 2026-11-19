"""Поиск внешних программ, без которых yt-dlp работает хуже: JS-движка и ffmpeg."""

import glob as globlib
import os
import shutil

# Deno — выбор yt-dlp по умолчанию, Node чаще уже установлен, Bun — на всякий случай.
JS_RUNTIME_ORDER = ("deno", "node", "bun")
KNOWN_JS_PATHS = (
    ("node", os.path.expandvars(r"%ProgramFiles%\nodejs\node.exe")),
    ("deno", os.path.expandvars(r"%USERPROFILE%\.deno\bin\deno.exe")),
)
WINGET_FFMPEG_PATTERN = os.path.expandvars(
    r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\*FFmpeg*\**\bin\ffmpeg.exe"
)


def find_js_runtime(which=shutil.which, isfile=os.path.isfile):
    """(имя, путь) первого найденного JS-движка или None.

    Без него YouTube отдаёт урезанный набор форматов, а то и ничего.
    """
    for name in JS_RUNTIME_ORDER:
        path = which(name)
        if path:
            return name, path
    for name, path in KNOWN_JS_PATHS:
        if isfile(path):
            return name, path
    return None


def find_ffmpeg_dir(which=shutil.which, glob=globlib.glob):
    """Папка с ffmpeg: из PATH, иначе самая свежая установка через winget."""
    path = which("ffmpeg")
    if path:
        return os.path.dirname(path)
    matches = sorted(glob(WINGET_FFMPEG_PATTERN, recursive=True))
    return os.path.dirname(matches[-1]) if matches else None
