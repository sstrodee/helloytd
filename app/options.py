"""Сборка параметров yt-dlp из выбора в окне и разбор его ошибок."""

import os
import re
from dataclasses import dataclass

from yt_dlp.utils import download_range_func

from .formats import VIDEO_FORMAT, trim_label, video_format_sort
from .i18n import tr
from .links import redact_url_credentials

SUBTITLE_LANGS = ["ru", "en"]
# Каналы бывают на тысячи видео; в карточке хватит первых, скачать можно весь.
PLAYLIST_PREVIEW_LIMIT = 300
FRAGMENT_MAX_HEIGHT = 1080

# Ключ в настройках → (подпись в списке, кодек, битрейт).
AUDIO_CHOICES = {
    "mp3-320": ("mp3, 320 кбит/с", "mp3", 320),
    "mp3-192": ("mp3, 192 кбит/с", "mp3", 192),
    "m4a": ("m4a, оригинал без перекодирования", "m4a", None),
}

SINGLE_TEMPLATE = "%(title).140B [%(id)s].%(ext)s"
PLAYLIST_TEMPLATE = "%(playlist_title).70B [%(playlist_id)s]/%(playlist_index)03d - %(title).140B [%(id)s].%(ext)s"

ERROR_MESSAGES = {
    "network": "Нет связи с YouTube. Нужен включённый VPN: его прокси находится автоматически.",
    "bot_check": "YouTube требует подтвердить, что запрос не от бота. Помогает вход в YouTube в браузере и повтор.",
    "age": "Видео 18+: YouTube отдаёт его только после входа в аккаунт в браузере.",
    "private": "Видео приватное или только для спонсоров канала: нужен аккаунт с доступом.",
    "unavailable": "Видео недоступно: удалено, скрыто или заблокировано в этой стране.",
    "ffmpeg": "Не найден ffmpeg: без него не склеить видео со звуком и не сделать mp3.",
    "bad_url": "Это не похоже на ссылку на видео.",
    "format": "У этого видео нет такого качества. Подойдёт качество ниже или «лучшее».",
    "forbidden": "YouTube отклонил запрос (403). Обычно помогает обновление yt-dlp в настройках.",
    "rate_limit": "YouTube временно ограничил запросы. Повтор через несколько минут.",
    "disk_full": "Закончилось место на диске.",
    "no_access": "Нет доступа к папке сохранения, нужна другая папка.",
    "unknown": "Не получилось скачать.",
}

# Порядок важен: частные случаи раньше общих (403 раньше сетевых, бот раньше приватного).
_ERROR_PATTERNS = (
    ("ffmpeg", ("ffmpeg not found", "ffprobe and ffmpeg not found", "ffmpeg is not installed")),
    ("bad_url", ("unsupported url", "is not a valid url")),
    ("bot_check", ("not a bot",)),
    ("age", ("confirm your age", "age-restricted", "age restricted")),
    ("private", ("private video", "members-only", "members only")),
    ("unavailable", (
        "video unavailable", "this video is unavailable", "has been removed",
        "not available in your country", "account associated with this video has been terminated",
    )),
    ("format", ("requested format is not available",)),
    ("rate_limit", ("http error 429", "too many requests")),
    ("forbidden", ("http error 403",)),
    ("disk_full", ("no space left", "errno 28", "winerror 112")),
    ("no_access", ("permission denied", "errno 13", "access is denied", "winerror 5]")),
    ("network", (
        "ssl", "eof occurred", "timed out", "10054", "10053", "10060", "10061",
        "connection reset", "connection refused", "connection aborted", "getaddrinfo",
        "name resolution", "proxyerror", "unable to connect", "network is unreachable",
        "remote end closed", "remotedisconnected",
    )),
)
_COOKIE_KINDS = {"bot_check", "age", "private"}


@dataclass(frozen=True)
class DownloadRequest:
    url: str
    out_dir: str
    mode: str = "video"            # "video" | "audio"
    max_height: int | None = None  # None — лучшее доступное
    audio_codec: str = "mp3"       # "mp3" | "m4a"
    audio_bitrate: int | None = 320
    subtitles: bool = False
    trim: tuple | None = None      # (начало, конец | None) в секундах
    is_playlist: bool = False
    playlist_items: tuple | None = None  # номера с 1; None — весь плейлист


def build_ydl_options(request, *, proxy=None, js_runtime=None, ffmpeg_dir=None, cookies_browser=None):
    trimming = bool(request.trim) and not request.is_playlist
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": not request.is_playlist,
        # Папка — через paths, а не в шаблоне: «%» в имени папки сломал бы шаблон.
        "paths": {"home": request.out_dir},
        "outtmpl": {"default": _output_template(request)},
        "retries": 10,
        "fragment_retries": 10,
        "skip_unavailable_fragments": False,
        "concurrent_fragment_downloads": 4,
        "overwrites": False,
    }
    postprocessors = []

    if request.mode == "audio":
        opts["format"] = (
            "bestaudio[ext=m4a]/bestaudio/best" if request.audio_codec == "m4a" else "bestaudio/best"
        )
        # 5.1-дорожка тяжелее втрое, а в MP3 всё равно станет стерео.
        opts["format_sort"] = ["channels:2"]
        opts["writethumbnail"] = True
        # Превью YouTube отдаёт в webp, а в MP3 надёжно встаёт только jpg.
        postprocessors.append({"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"})
        postprocessors.append({
            "key": "FFmpegExtractAudio",
            "preferredcodec": request.audio_codec,
            "preferredquality": str(request.audio_bitrate) if request.audio_bitrate else None,
        })
    else:
        opts["format"] = VIDEO_FORMAT
        opts["format_sort"] = video_format_sort(request.max_height)
        opts["merge_output_format"] = "mp4"
        if request.subtitles:
            opts["writesubtitles"] = True
            opts["writeautomaticsub"] = True
            opts["subtitleslangs"] = list(SUBTITLE_LANGS)
            postprocessors.append({"key": "FFmpegSubtitlesConvertor", "format": "srt", "when": "before_dl"})

    # Главы размечены по всему ролику — во фрагменте они указывали бы мимо.
    postprocessors.append({"key": "FFmpegMetadata", "add_metadata": True, "add_chapters": not trimming})
    if request.mode == "audio":
        postprocessors.append({"key": "EmbedThumbnail", "already_have_thumbnail": False})
    opts["postprocessors"] = postprocessors

    if request.is_playlist:
        # Одно удалённое видео не должно останавливать весь плейлист.
        opts["ignoreerrors"] = True
        if request.playlist_items:
            opts["playlist_items"] = ",".join(str(index) for index in sorted(request.playlist_items))
    elif trimming:
        # Обычный DASH-файл на глубокой отметке может минутами не отвечать FFmpeg.
        # HLS разбит на короткие сегменты: нужная минута открывается сразу, без
        # скачивания всего ролика. YouTube отдаёт HLS до 1080p.
        start, end = request.trim
        opts["external_downloader_args"] = {"ffmpeg_i": ["-rw_timeout", "15000000"]}
        if request.mode == "video":
            height = min(request.max_height or FRAGMENT_MAX_HEIGHT, FRAGMENT_MAX_HEIGHT)
            opts["format"] = (
                f"bestvideo[protocol=m3u8_native][height<={height}]"
                f"+bestaudio[protocol=m3u8_native]/best[protocol=m3u8_native][height<={height}]"
                f"/bestvideo[height<=?{height}]+bestaudio/best[height<=?{height}]"
            )
            # Точная граница требует перекодировать только выбранные секунды.
            opts["force_keyframes_at_cuts"] = True
            opts["external_downloader_args"]["ffmpeg_o"] = ["-preset", "veryfast", "-crf", "18"]
        else:
            opts["format"] = "bestaudio[protocol=m3u8_native]/" + opts["format"]
            opts["force_keyframes_at_cuts"] = False
        opts["download_ranges"] = download_range_func(
            None, [(start, end if end is not None else float("inf"))],
        )

    opts.update(_network_options(proxy, js_runtime, cookies_browser))
    if ffmpeg_dir:
        opts["ffmpeg_location"] = ffmpeg_dir
    return opts


def info_ydl_options(as_playlist, *, proxy=None, js_runtime=None, cookies_browser=None):
    """Параметры для быстрой карточки: плейлист — одним списком, не открывая каждое видео."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "noplaylist": not as_playlist,
        "playlistend": PLAYLIST_PREVIEW_LIMIT,
    }
    opts.update(_network_options(proxy, js_runtime, cookies_browser))
    return opts


def run_with_cookie_retry(attempt, browser, mode, on_retry=None):
    """attempt(браузер или None) → результат.

    В режиме «auto» сначала пробуем без cookies и только если YouTube упёрся
    во вход — ещё раз с cookies браузера. Так аккаунт не светится в каждом запросе.
    """
    first = browser if mode == "always" else None
    try:
        return attempt(first)
    except Exception as error:
        if mode != "auto" or first or not needs_cookies(str(error)):
            raise
    if on_retry:
        on_retry()
    return attempt(browser)


def summarize_result(info, is_playlist, *, path_ready=bool):
    """(успех, сообщение, путь к файлу или к папке плейлиста) по ответу yt-dlp."""
    if not info:
        return False, tr(ERROR_MESSAGES["unknown"]), ""
    if not is_playlist:
        path = _downloaded_path(info)
        return (True, "", path) if path_ready(path) else (False, tr(ERROR_MESSAGES["unknown"]), "")

    entries = list(info.get("entries") or [])
    paths = [path for path in (_downloaded_path(entry) for entry in entries if entry) if path_ready(path)]
    if not paths:
        return False, tr("Ни одно видео из плейлиста не скачалось."), ""
    folder = os.path.dirname(paths[0])
    if len(paths) < len(entries):
        return True, tr("Скачано {done} из {total} — остальные недоступны.",
                        done=len(paths), total=len(entries)), folder
    return True, "", folder


def _downloaded_path(info):
    downloads = info.get("requested_downloads") or []
    return downloads[0].get("filepath", "") if downloads else ""


def _network_options(proxy, js_runtime, cookies_browser):
    opts = {"proxy": proxy or "", "socket_timeout": 15}
    if js_runtime:
        name, path = js_runtime
        opts["js_runtimes"] = {name: {"path": path}}
    if cookies_browser:
        opts["cookiesfrombrowser"] = (cookies_browser,)
    return opts


def _output_template(request):
    if request.is_playlist:
        return PLAYLIST_TEMPLATE
    if request.trim:
        start, end = request.trim
        return f"%(title).125B [%(id)s] [{trim_label(start, end)}].%(ext)s"
    return SINGLE_TEMPLATE


def classify_error(message):
    text = (message or "").lower()
    for kind, needles in _ERROR_PATTERNS:
        if any(needle in text for needle in needles):
            return kind
    return "unknown"


def needs_cookies(message):
    """Стоит ли повторить попытку с cookies из браузера."""
    return classify_error(message) in _COOKIE_KINDS


def friendly_error(message):
    kind = classify_error(message)
    if kind != "unknown":
        return tr(ERROR_MESSAGES[kind])
    detail = _error_detail(message)
    message = tr(ERROR_MESSAGES["unknown"])
    return f"{message} {detail}" if detail else message


def _error_detail(message):
    lines = (message or "").strip().splitlines()
    if not lines:
        return ""
    text = re.sub(r"^ERROR:\s*", "", lines[-1].strip())
    text = re.sub(r"^\[[\w:]+\]\s*[\w-]+:\s*", "", text)  # «[youtube] abc123: »
    return redact_url_credentials(text.strip())[:400]
