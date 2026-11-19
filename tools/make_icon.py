r"""Рисует assets/icon.png: «Hi» на жидком градиенте поля, в форме iOS-значка.

    dist\helloytd\runtime\python.exe tools\make_icon.py

Форма — суперэллипс |x|^n + |y|^n = 1: кривизна угла нарастает плавно, без
излома там, где у обычного скругления дуга встречает прямую. Так выглядят
значки iOS. Исходный рисунок автора — design-refs/icon-hi-original.png.
"""

import math
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFontMetricsF, QGuiApplication, QImage, QPainter, QPainterPath  # noqa: E402

from app import theme  # noqa: E402

SIZE = 1024
MARGIN = 0.03         # доля стороны: край суперэллипса не упирается в край картинки
EXPONENT = 5.0        # степень суперэллипса; у значков iOS — около пяти
CAP_HEIGHT = 0.46     # высота заглавной «H» от стороны значка, как на рисунке автора
# Происхождение картинки — в её же метаданных, под ключом, который читает impeccable embed-prompt.
ORIGIN = ("origin: drawn in code by tools/make_icon.py (theme.paint_liquid gradient, cream Instrument "
          "Serif Hi, superellipse n=5 mask); replaces the owner's artwork kept at design-refs/icon-hi-original.png")


def squircle(center, radius, exponent=EXPONENT, steps=720):
    path = QPainterPath()
    for index in range(steps + 1):
        angle = 2 * math.pi * index / steps
        cos, sin = math.cos(angle), math.sin(angle)
        x = math.copysign(abs(cos) ** (2 / exponent), cos) * radius
        y = math.copysign(abs(sin) ** (2 / exponent), sin) * radius
        point = QPointF(center + x, center + y)
        path.moveTo(point) if index == 0 else path.lineTo(point)
    path.closeSubpath()
    return path


def render(size=SIZE):
    theme.load_fonts()
    image = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
    shape = squircle(size / 2, size / 2 * (1 - 2 * MARGIN))
    painter.setClipPath(shape)
    theme.paint_liquid(painter, size, size)

    # «Hi» по центру: размер шрифта подобран так, чтобы заглавная была нужной высоты.
    font = theme.serif_font(100)
    cap = QFontMetricsF(font).capHeight()
    font.setPixelSize(round(100 * CAP_HEIGHT * size / cap))
    metrics = QFontMetricsF(font)
    bounds = metrics.tightBoundingRect("Hi")
    baseline = size / 2 + metrics.capHeight() / 2
    left = size / 2 - bounds.width() / 2 - bounds.left()
    painter.setFont(font)
    painter.setPen(QColor(theme.C["field_ink"]))
    painter.drawText(QPointF(left, baseline), "Hi")
    painter.end()
    image.setText("impeccable:prompt", ORIGIN)
    return image


if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    target = PROJECT / "assets" / "icon.png"
    render().save(str(target))
    print(f"готово: {target}")
