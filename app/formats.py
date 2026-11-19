"""Чистые функции: format-строки yt-dlp, таймкоды, единицы измерения."""

import math

_SIZE_UNITS = ("Б", "КБ", "МБ", "ГБ", "ТБ")
_UNKNOWN = "—"

# Видео и звук в mp4/m4a склеиваются без перекодирования; дальше — любые.
VIDEO_FORMAT = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"

# Качества YouTube и номинальная длинная сторона кадра для каждого.
_TIERS = (
    (2160, 3840), (1440, 2560), (1080, 1920), (720, 1280),
    (480, 854), (360, 640), (240, 426), (144, 256),
)
# Что предлагать в списке: ниже 360p выбирать уже нечего.
QUALITY_TIERS = (2160, 1440, 1080, 720, 480, 360)
_TIER_SUFFIX = {2160: "4K", 1440: "2K", 1080: "Full HD", 720: "HD"}
# Кадр чуть меньше номинала (1918×1080, 1280×718) всё ещё считается этим качеством.
_TIER_TOLERANCE = 0.9


def video_format_sort(max_height):
    """Порядок предпочтения форматов: разрешение, частота кадров, затем кодек.

    Потолок задаётся через res — это меньшая сторона кадра, поэтому он
    одинаково работает для обычных, вертикальных и широкоформатных роликов.
    H.264 предпочитается только при равном разрешении: он открывается любым
    плеером, а «Лучшее» всё равно получит 4K в VP9/AV1, где H.264 нет.
    """
    if max_height is None:
        resolution = "res"
    elif max_height <= 0:
        raise ValueError(f"высота должна быть больше нуля, получено {max_height!r}")
    else:
        resolution = f"res:{max_height}"
    # Стерео: 5.1-дорожка YouTube тяжелее картинки в 360p, а на обычных колонках звучит так же.
    return [resolution, "fps", "vcodec:h264", "channels:2", "acodec:m4a"]


def tier_of(width, height):
    """Качество по размеру кадра так, как его называет YouTube: 1920×800 — это 1080p."""
    sides = [side for side in (width, height) if side]
    if not sides:
        return None
    short_side, long_side = min(sides), max(sides)
    for tier, nominal_long in _TIERS:
        if short_side >= tier * _TIER_TOLERANCE or long_side >= nominal_long * _TIER_TOLERANCE:
            return tier
    return None


def quality_tiers(formats):
    """Качества для выбора: от лучшего доступного вниз."""
    tiers = [tier_of(fmt.get("width"), fmt.get("height")) for fmt in formats if _is_video(fmt)]
    best = max((tier for tier in tiers if tier), default=None)
    if best is None:
        return []
    return [tier for tier in QUALITY_TIERS if tier <= best]


def tier_name(tier):
    suffix = _TIER_SUFFIX.get(tier)
    return f"{tier}p, {suffix}" if suffix else f"{tier}p"


def _is_video(fmt):
    # У раскадровок vcodec тоже "none", хотя размер кадра есть.
    return fmt.get("vcodec") != "none" and bool(fmt.get("width") or fmt.get("height"))


def parse_timecode(text):
    """Переводит «90», «1:30» или «1:02:03.5» в секунды."""
    raw = "" if text is None else str(text).strip()
    if not raw:
        raise ValueError("таймкод пустой")

    parts = raw.split(":")
    if len(parts) > 3 or len(raw) > 64:
        raise ValueError(f"не похоже на время: {raw!r}")

    try:
        # Дробная часть допустима только в секундах.
        numbers = [
            float(part) if index == len(parts) - 1 else int(part)
            for index, part in enumerate(parts)
        ]
    except ValueError:
        raise ValueError(f"не похоже на время: {raw!r}") from None

    if not math.isfinite(numbers[-1]):
        raise ValueError("таймкод должен быть конечным числом")
    if any(number < 0 for number in numbers):
        raise ValueError(f"время не может быть отрицательным: {raw!r}")
    if any(number >= 60 for number in numbers[1:]):
        raise ValueError(f"минуты и секунды должны быть меньше 60: {raw!r}")

    total = 0.0
    for number in numbers:
        total = total * 60 + number
    return float(total)


def parse_range(start, end, *, duration=None, required=False):
    """Границы обрезки в секундах, либо None если обрезка не задана.

    Пустое начало — с начала видео, пустой конец — до конца (None).
    """
    start_raw = ("" if start is None else str(start)).strip()
    end_raw = ("" if end is None else str(end)).strip()
    if not start_raw and not end_raw:
        if required:
            raise ValueError("нужно указать начало или конец фрагмента")
        return None

    start_seconds = parse_timecode(start_raw) if start_raw else 0.0
    end_seconds = parse_timecode(end_raw) if end_raw else None
    if end_seconds is not None and end_seconds <= start_seconds:
        raise ValueError("конец обрезки должен быть позже начала")
    if duration is not None and duration > 0:
        if start_seconds >= duration:
            raise ValueError("начало фрагмента за пределами видео")
        if end_seconds is not None and end_seconds > duration:
            raise ValueError("конец фрагмента за пределами видео")
    return (start_seconds, end_seconds)


def trim_label(start, end):
    """Подпись фрагмента для имени файла: «1.30-4.00», «1.02.03-конец».

    Двоеточие в именах файлов Windows запрещено, поэтому разделитель — точка.
    """
    end_text = "конец" if end is None else _clock(end)
    start_text = _clock(start)
    return f"{start_text}-{end_text}"


def _clock(seconds):
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    _, point, fraction = repr(seconds).partition(".")
    if "e" in repr(seconds):
        from decimal import Decimal
        _, point, fraction = format(Decimal(str(seconds)), "f").partition(".")
    suffix = f",{fraction}" if point and fraction.strip("0") else ""
    if hours:
        return f"{hours}.{minutes:02d}.{secs:02d}{suffix}"
    return f"{minutes}.{secs:02d}{suffix}"


def format_bytes(value):
    """«1,5 МБ». Неизвестный размер — тире."""
    if value is None or value < 0:
        return _UNKNOWN
    size = float(value)
    if size < 1024:
        return f"{int(size)} {_SIZE_UNITS[0]}"
    for unit in _SIZE_UNITS[1:]:
        size /= 1024.0
        if size < 1024 or unit == _SIZE_UNITS[-1]:
            return f"{size:.1f} {unit}".replace(".", ",")
    raise AssertionError("недостижимо")


def format_speed(value):
    """«1,0 МБ/с». Неизвестная скорость — тире."""
    if value is None or value < 0:
        return _UNKNOWN
    return f"{format_bytes(value)}/с"


def format_eta(seconds):
    """«45 с», «1 мин 30 с», «1 ч 2 мин». Неизвестный остаток — тире."""
    if seconds is None or seconds < 0:
        return _UNKNOWN
    total = int(seconds)
    if total < 60:
        return f"{total} с"
    if total < 3600:
        return f"{total // 60} мин {total % 60} с"
    return f"{total // 3600} ч {(total % 3600) // 60} мин"


def format_duration(seconds):
    """«0:19», «10:35», «1:02:03» — как на YouTube. Неизвестная длительность — пусто."""
    if seconds is None:
        return ""
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
