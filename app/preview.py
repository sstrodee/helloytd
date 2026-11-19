"""Карточка того, что откроется по ссылке: из ответа yt-dlp — только то, что нужно окну."""

from dataclasses import dataclass

from .formats import quality_tiers
from .links import has_playlist_param

# Превью в окне около 200 пикселей шириной — крупнее качать незачем.
_THUMBNAIL_MIN_WIDTH = 320


@dataclass(frozen=True)
class Preview:
    url: str
    kind: str                  # "video" | "playlist"
    title: str
    uploader: str
    duration: float | None
    thumbnail_url: str | None
    tiers: tuple = ()          # доступные качества; у плейлиста заранее неизвестны
    has_subtitles: bool = False
    entries: tuple = ()        # у плейлиста: (номер, название, длительность)
    in_playlist: bool = False  # видео открыто по ссылке с &list=


def summarize(info, url):
    title = info.get("title") or "Без названия"
    uploader = info.get("uploader") or info.get("channel") or ""

    if info.get("_type") == "playlist":
        raw_entries = list(info.get("entries") or [])
        # Номера сохраняем исходные — по ним потом выбираются видео для скачивания.
        entries = tuple(
            (number, entry.get("title") or "Без названия", entry.get("duration"))
            for number, entry in enumerate(raw_entries, start=1)
            if entry
        )
        thumbnail = _pick_thumbnail(info) or next(
            (found for entry in raw_entries if entry and (found := _pick_thumbnail(entry))), None
        )
        return Preview(url=url, kind="playlist", title=title, uploader=uploader,
                       duration=None, thumbnail_url=thumbnail, entries=entries)

    return Preview(
        url=url,
        kind="video",
        title=title,
        uploader=uploader,
        duration=info.get("duration"),
        thumbnail_url=_pick_thumbnail(info),
        tiers=tuple(quality_tiers(info.get("formats") or [])),
        has_subtitles=bool(info.get("subtitles") or info.get("automatic_captions")),
        in_playlist=has_playlist_param(url),
    )


def _pick_thumbnail(info):
    """Самая маленькая картинка, которая ещё не мылит; если таких нет — что есть."""
    thumbnails = [thumb for thumb in (info.get("thumbnails") or []) if thumb.get("url")]
    sized = sorted((thumb for thumb in thumbnails if thumb.get("width")), key=lambda thumb: thumb["width"])
    for thumb in sized:
        if thumb["width"] >= _THUMBNAIL_MIN_WIDTH:
            return thumb["url"]
    if sized:
        return sized[-1]["url"]
    if thumbnails:
        return thumbnails[-1]["url"]
    return info.get("thumbnail")
