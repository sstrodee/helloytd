"""Один общий прогресс из событий yt-dlp.

Видео и звук качаются отдельными потоками, каждый от 0 до 100%, а видео
плейлиста — по очереди. Пользователю нужна одна полоса, которая не скачет.
"""

from dataclasses import dataclass, replace

from .formats import format_eta, format_speed

# Ключи — как шаги называет сам yt-dlp (PostProcessor.pp_key: без «FFmpeg» и «PP»).
STAGE_LABELS = {
    "SubtitlesConvertor": "Подготовка субтитров…",
    "ThumbnailsConvertor": "Подготовка обложки…",
    "Merger": "Склейка видео и звука…",
    "ExtractAudio": "Конвертация звука…",
    "Metadata": "Запись названия и глав…",
    "EmbedThumbnail": "Встраивание обложки…",
}
DOWNLOADING = "Скачивание"
_SETTLE_SECONDS = 1.0


@dataclass(frozen=True)
class Progress:
    fraction: float | None = None  # 0..1; None — сколько осталось, неизвестно
    speed: float | None = None     # байт в секунду
    eta: float | None = None       # секунд до конца
    stage: str = "Подготовка…"
    item: int | None = None        # номер видео в плейлисте
    item_count: int | None = None


class ProgressTracker:
    def __init__(self):
        self._video_id = None
        self._finished_streams = set()
        self._plans = {}
        self._last = Progress()

    def plan(self, info):
        """Из каких потоков соберётся видео — с шага before_dl.

        В событиях загрузки yt-dlp этот список уже не передаёт (удаляет
        requested_formats у каждого потока), а без него полоса после картинки
        откатывалась бы на ноль и шла заново на звуке.
        """
        self._plans[info.get("id")] = list(info.get("requested_formats") or [])

    def on_download(self, hook):
        info = hook.get("info_dict") or {}
        if "format_id" not in info:
            # Субтитры и прочие побочные файлы качаются тем же загрузчиком,
            # но к полосе видео не относятся.
            return self._last
        if info.get("id") != self._video_id:
            self._video_id = info.get("id")
            self._finished_streams = set()

        stream_id = info.get("format_id")
        if hook.get("status") == "finished":
            self._finished_streams.add(stream_id)
            stream_fraction = 1.0
        elif hook.get("fragment_count"):
            # HLS/DASH: оценка размера в начале скачет (первое событие — 100%),
            # а счёт фрагментов растёт ровно.
            stream_fraction = min((hook.get("fragment_index") or 0) / hook["fragment_count"], 1.0)
        else:
            total = hook.get("total_bytes") or hook.get("total_bytes_estimate")
            done = hook.get("downloaded_bytes") or 0
            stream_fraction = min(done / total, 1.0) if total else None

        fraction = self._video_fraction(info, stream_id, stream_fraction)
        item, count = info.get("playlist_autonumber"), info.get("n_entries")
        if fraction is not None and item and count:
            fraction = ((item - 1) + fraction) / count

        # Первые полсекунды скорость считается по паре килобайт — «455 Б/с» только пугает.
        settled = (hook.get("elapsed") or _SETTLE_SECONDS) >= _SETTLE_SECONDS
        speed, eta = (hook.get("speed"), hook.get("eta")) if settled else (None, None)
        self._last = Progress(fraction, speed, eta, DOWNLOADING, item, count)
        return self._last

    def on_postprocess(self, hook):
        label = STAGE_LABELS.get(hook.get("postprocessor"))
        if hook.get("status") != "started" or not label:
            return None
        self._last = replace(self._last, stage=label, speed=None, eta=None)
        return self._last

    def _video_fraction(self, info, stream_id, stream_fraction):
        """Доля текущего видео: потоки весят по ожидаемому размеру, иначе поровну."""
        streams = self._plans.get(info.get("id")) or []
        ids = [stream.get("format_id") for stream in streams]
        if len(ids) < 2 or stream_id not in ids:
            return stream_fraction
        if stream_fraction is None:
            return None

        sizes = [stream.get("filesize") or stream.get("filesize_approx") for stream in streams]
        if all(sizes):
            weights = sizes
        else:
            # Размер неизвестен (4K по HLS) — картинка всё равно весит в разы больше звука.
            weights = [1 if stream.get("vcodec") == "none" else 9 for stream in streams]
        done = 0.0
        for other_id, weight in zip(ids, weights):
            if other_id == stream_id:
                done += weight * stream_fraction
            elif other_id in self._finished_streams:
                done += weight
        return done / sum(weights)


def describe_detail(progress):
    """Подробности без процента: «2,1 МБ/с, осталось 12 с». Процент окно показывает крупно отдельно."""
    if progress is None:
        return Progress().stage
    head = (
        f"Видео {progress.item} из {progress.item_count}"
        if progress.item and progress.item_count else None
    )
    if progress.stage != DOWNLOADING:
        return ", ".join(part for part in (head, progress.stage) if part)

    parts = [head] if head else []
    if progress.speed:
        parts.append(format_speed(progress.speed))
    if progress.eta is not None:
        parts.append(f"осталось {format_eta(progress.eta)}")
    return ", ".join(parts) if parts else f"{DOWNLOADING}…"
