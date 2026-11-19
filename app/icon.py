"""Значок приложения — «Hi» на градиенте, рисунок автора (assets/icon.png)."""

import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QIcon, QImage, QPixmap

ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)
ARTWORK = Path(__file__).resolve().parent.parent / "assets" / "icon.png"


def _artwork(size):
    # QImage, а не QPixmap: так значок готовится и без запущенного приложения (сборка).
    image = QImage(str(ARTWORK))
    # Уменьшаем по половине за шаг: одним махом с 858 до 16 буквы рассыпаются.
    while image.width() > size * 2:
        image = image.scaled(image.width() // 2, image.height() // 2,
                             Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    return image.scaled(size, size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)


def make_icon(size=256):
    return QPixmap.fromImage(_artwork(size))


def app_icon():
    icon = QIcon()
    for size in ICON_SIZES:
        icon.addPixmap(make_icon(size))
    return icon


def write_ico(path):
    """Многоразмерный .ico из PNG-кадров — для helloytd.exe."""
    frames = []
    for size in ICON_SIZES:
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.WriteOnly)
        _artwork(size).save(buffer, "PNG")
        buffer.close()
        frames.append((size, bytes(data)))

    header = struct.pack("<HHH", 0, 1, len(frames))
    offset = len(header) + 16 * len(frames)
    entries, images = b"", b""
    for size, png in frames:
        side = 0 if size >= 256 else size  # 0 в заголовке ICO означает 256
        entries += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(png), offset)
        images += png
        offset += len(png)
    with open(path, "wb") as file:
        file.write(header + entries + images)
