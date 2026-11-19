"""Уборка недокачанного после отмены."""

import gc
import glob
import os
import time


def remove_partial_files(paths, attempts=6, delay=0.25):
    """Удаляет сам файл, его .part, .ytdl и фрагменты .part-FragN.

    На Windows только что отменённая загрузка ещё держит .part открытым: его
    не отпускают объекты, на которые ссылается трассировка исключения. Поэтому
    сначала собираем мусор, а занятые файлы пробуем удалить ещё несколько раз.
    """
    pending = set()
    for path in paths:
        pending.update((path, f"{path}.part", f"{path}.ytdl"))
        pending.update(glob.glob(glob.escape(path) + ".part-Frag*"))
    gc.collect()

    for attempt in range(attempts):
        for candidate in list(pending):
            try:
                os.remove(candidate)
            except FileNotFoundError:
                pass
            except OSError:
                continue  # занят — попробуем на следующем круге
            pending.discard(candidate)
        if not pending:
            return
        if attempt < attempts - 1:
            time.sleep(delay)
