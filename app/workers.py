"""Фоновые потоки: проверка сети, карточка по ссылке, скачивание.

yt-dlp работает блокирующе, поэтому всё сетевое живёт в QThread, а в окно
возвращается сигналами. Сигналы подключаются к методам окна — тогда Qt сам
доставляет их в главный поток.
"""

import logging
import os
import time
from dataclasses import dataclass

from PySide6.QtCore import QThread, Signal
from yt_dlp import YoutubeDL
from yt_dlp.postprocessor import get_postprocessor
from yt_dlp.postprocessor.common import PostProcessor
from yt_dlp.utils import DownloadCancelled

from .cleanup import remove_partial_files
from .environment import find_ffmpeg_dir, find_js_runtime
from .links import redact_url_credentials
from .network import detect_route, probe
from .options import (
    build_ydl_options,
    friendly_error,
    info_ydl_options,
    needs_cookies,
    run_with_cookie_retry,
    summarize_result,
)
from .preview import summarize
from .progress import Progress, ProgressTracker

log = logging.getLogger("ytdl")

COOKIE_RETRY_STAGE = "YouTube просит вход, повтор с cookies из браузера…"
_PROGRESS_INTERVAL = 0.15  # секунд между обновлениями полосы
THUMBNAIL_LIMIT = 2 * 1024 * 1024


@dataclass(frozen=True)
class Environment:
    proxy: str | None = None
    reachable: bool | None = None  # None — ещё проверяем
    js_runtime: tuple | None = None
    ffmpeg_dir: str | None = None


class StreamPlanPP(PostProcessor):
    """Шаг перед загрузкой: передаёт трекеру, из каких потоков соберётся видео."""

    def __init__(self, downloader, on_plan):
        super().__init__(downloader)
        self._on_plan = on_plan

    def run(self, info):
        self._on_plan(info)
        return [], info


class _YtdlpLog:
    """Предупреждения и ошибки yt-dlp — в журнал; ошибки ещё и запоминаем для итога."""

    def __init__(self):
        self.errors = []

    def debug(self, message):
        pass

    def info(self, message):
        pass

    def warning(self, message):
        log.warning("%s", redact_url_credentials(message))

    def error(self, message):
        safe = redact_url_credentials(message)
        self.errors.append(safe)
        log.error("%s", safe)


def fetch_bytes(url, proxy, timeout=10):
    """Картинку качаем тем же маршрутом: i.ytimg.com режут так же, как сам YouTube."""
    if not url:
        return None
    params = {"quiet": True, "no_warnings": True, "proxy": proxy or "", "socket_timeout": timeout}
    deadline = time.monotonic() + timeout
    try:
        with YoutubeDL(params) as ydl, ydl.urlopen(url) as response:
            buffer = bytearray()
            while chunk := response.read(64 * 1024):
                buffer.extend(chunk)
                if len(buffer) > THUMBNAIL_LIMIT or time.monotonic() > deadline:
                    return None
            return bytes(buffer)
    except Exception as error:  # noqa: BLE001 — без превью карточка всё равно работает
        log.info("thumbnail failed: %s", redact_url_credentials(str(error)))
        return None


class EnvironmentProbe(QThread):
    ready = Signal(object)

    def __init__(self, route_mode, manual_proxy, parent=None):
        super().__init__(parent)
        self._route_mode = route_mode
        manual = (manual_proxy or "").strip()
        self._manual_proxy = manual if not manual or "://" in manual else f"http://{manual}"

    def run(self):
        js_runtime, ffmpeg_dir = find_js_runtime(), find_ffmpeg_dir()
        if self._route_mode == "direct":
            proxy, reachable = None, probe(None)
        elif self._route_mode == "manual" and self._manual_proxy:
            proxy, reachable = self._manual_proxy, probe(self._manual_proxy)
        else:
            proxy, reachable = detect_route()
        log.info("environment: proxy=%r reachable=%s js=%r ffmpeg=%r",
                 redact_url_credentials(proxy or ""), reachable, js_runtime, ffmpeg_dir)
        self.ready.emit(Environment(proxy, reachable, js_runtime, ffmpeg_dir))


class InfoFetcher(QThread):
    done = Signal(int, object, object)  # номер запроса, Preview, байты превью или None
    failed = Signal(int, str)
    retrying = Signal(int, str)

    def __init__(self, serial, url, env, cookies_browser, cookies_mode, as_playlist=False, parent=None):
        super().__init__(parent)
        self.serial = serial
        self.url = url
        self._env = env
        self._browser = cookies_browser
        self._cookies_mode = cookies_mode
        self._as_playlist = as_playlist

    def run(self):
        try:
            info = run_with_cookie_retry(
                self._extract, self._browser, self._cookies_mode,
                on_retry=lambda: self.retrying.emit(self.serial, COOKIE_RETRY_STAGE),
            )
            preview = summarize(info, self.url)
        except Exception as error:  # noqa: BLE001 — любую ошибку показываем человеческим текстом
            log.warning("preview failed: %s", redact_url_credentials(str(error)))
            self.failed.emit(self.serial, friendly_error(str(error)))
            return
        self.done.emit(self.serial, preview, fetch_bytes(preview.thumbnail_url, self._env.proxy))

    def _extract(self, cookies_browser):
        opts = info_ydl_options(
            self._as_playlist,
            proxy=self._env.proxy,
            js_runtime=self._env.js_runtime,
            cookies_browser=cookies_browser,
        )
        opts["logger"] = _YtdlpLog()
        with YoutubeDL(opts) as ydl:
            return ydl.sanitize_info(ydl.extract_info(self.url, download=False))


class DownloadWorker(QThread):
    progressed = Signal(int, object)        # id задачи, Progress
    completed = Signal(int, bool, str, str)  # id, успех, сообщение, путь

    def __init__(self, job, env, cookies_browser, cookies_mode, parent=None):
        super().__init__(parent)
        self._job_id = job.id
        self._request = job.request
        self._env = env
        self._browser = cookies_browser
        self._cookies_mode = cookies_mode
        self._cancelled = False
        self._tracker = ProgressTracker()
        self._log = _YtdlpLog()
        self._last_emit = 0.0
        # Файлы видео, которое ещё не готово целиком: при отмене их убираем.
        self._partial_files = set()

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            info = run_with_cookie_retry(
                self._download, self._browser, self._cookies_mode,
                on_retry=lambda: self.progressed.emit(self._job_id, Progress(stage=COOKIE_RETRY_STAGE)),
            )
        except Exception as error:  # noqa: BLE001 — отмена и любые сбои yt-dlp
            cancelled = self._cancelled or isinstance(error, DownloadCancelled)
            message = "" if cancelled else friendly_error(str(error))
            if not cancelled:
                log.warning("download failed: %s", redact_url_credentials(str(error)))
        else:
            ok, message, path = summarize_result(info, self._request.is_playlist, path_ready=self._file_ready)
            if not ok and self._log.errors:
                message = friendly_error(self._log.errors[-1])
            self.completed.emit(self._job_id, ok, message, path)
            return

        # Уже вне except: трассировка отпущена вместе с открытыми ею файлами.
        # После обычной ошибки .part оставляем — «Повторить» докачает с того же места.
        if cancelled:
            remove_partial_files(self._partial_files)
        self.completed.emit(self._job_id, False, message, "")

    def _download(self, cookies_browser):
        if self._cancelled:
            raise DownloadCancelled()
        if self._request.trim:
            log.info("fragment download: range=%r", self._request.trim)
            self.progressed.emit(self._job_id, Progress(stage="Скачивание фрагмента…"))
        opts = build_ydl_options(
            self._request,
            proxy=self._env.proxy,
            js_runtime=self._env.js_runtime,
            ffmpeg_dir=self._env.ffmpeg_dir,
            cookies_browser=cookies_browser,
        )
        steps = opts.pop("postprocessors")
        opts["progress_hooks"] = [self._on_download]
        opts["postprocessor_hooks"] = [self._on_postprocess]
        opts["post_hooks"] = [self._on_video_done]
        opts["logger"] = self._log = _YtdlpLog()
        self._tracker = ProgressTracker()
        with YoutubeDL(opts) as ydl:
            self._add_steps(ydl, steps)
            info = ydl.sanitize_info(ydl.extract_info(self._request.url, download=True))

        # В плейлисте ошибки видео не прерывают скачивание, а только пишутся в журнал.
        # Если не скачалось ничего и причина — вход, пусть сработает повтор с cookies.
        if self._request.is_playlist and not summarize_result(info, True, path_ready=self._file_ready)[0]:
            last = self._log.errors[-1] if self._log.errors else ""
            if needs_cookies(last):
                raise RuntimeError(last)
        return info

    @staticmethod
    def _file_ready(path):
        try:
            return bool(path) and os.path.isfile(path) and os.path.getsize(path) > 0
        except OSError:
            return False

    def _on_video_done(self, _filepath):
        # Видео готово целиком (после всех шагов) — при отмене следующего его не трогаем.
        self._partial_files = set()

    def _add_steps(self, ydl, steps):
        """Шаги после скачивания по порядку; сам фрагмент уже забирает FFmpeg-загрузчик."""
        ydl.add_post_processor(StreamPlanPP(ydl, lambda info: self._tracker.plan(info)), when="before_dl")
        for spec in steps:
            spec = dict(spec)
            when = spec.pop("when", "post_process")
            ydl.add_post_processor(get_postprocessor(spec.pop("key"))(ydl, **spec), when=when)

    def _on_download(self, hook):
        if hook.get("status") == "downloading":
            self._partial_files.update(path for path in (hook.get("tmpfilename"), hook.get("filename")) if path)

        if self._cancelled:
            raise DownloadCancelled()

        progress = self._tracker.on_download(hook)
        now = time.monotonic()
        if hook.get("status") != "downloading" or now - self._last_emit >= _PROGRESS_INTERVAL:
            self._last_emit = now
            self.progressed.emit(self._job_id, progress)

    def _on_postprocess(self, hook):
        if self._cancelled and hook.get("status") == "started":
            raise DownloadCancelled()
        if hook.get("postprocessor") == "ThumbnailsConvertor" and hook.get("status") == "finished":
            # Обложка для MP3 пишется до звука; при отмене она тоже лишняя.
            info = hook.get("info_dict") or {}
            covers = (thumb.get("filepath") for thumb in info.get("thumbnails") or [])
            self._partial_files.update(cover for cover in covers if cover)
        progress = self._tracker.on_postprocess(hook)
        if progress is not None:
            self.progressed.emit(self._job_id, progress)

