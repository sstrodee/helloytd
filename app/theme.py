"""Тема: светлая панель-прибор и зернистое поле из иконки «Hi».

Instrument Serif — только латиница («Hi.», «helloytd»): кириллицы в нём нет,
а цифры по задумке набираются гротеском Golos. Цвет живёт только в поле;
на панели — чернила и заливки, без обводок.
"""

import ctypes
import os
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontDatabase,
    QImage,
    QPainter,
    QPalette,
    QPixmap,
    QRadialGradient,
    QTransform,
)

ASSETS = Path(__file__).resolve().parent.parent / "assets"
FONTS = ASSETS / "fonts"
SERIF = "Instrument Serif"
SANS = "Golos Text"

C = {
    "panel": "#eeede9",       # панель-прибор и фон диалогов
    "fill": "#e2e1db",        # заливка контролов на панели
    "fill_hi": "#d7d6cf",     # она же под курсором
    "card": "#fbfaf7",        # поле ввода в фокусе, кнопка внутри поля ссылки
    "ink": "#0f0f0d",
    "ink_soft": "#2f2f29",
    "ink_dim": "#6d6b64",
    "ink_faint": "#a3a199",
    "placeholder": "#5f5d57",  # подсказка в поле: 4,5:1 к заливке
    "off": "#86847e",         # пустой кружок отметки на панели: 3:1, как погасший диод на приборе
    "on_ink": "#fbfaf7",
    # Цвета иконки «Hi»: лайм → мята → морская волна → небо.
    "lime": "#c9dd45",
    "mint": "#acd38b",
    "aqua": "#8fcdcc",
    "sky": "#88cbdd",
    # Текст на синем поле — тёплый светлый, вторичный — он же прозрачнее, а не серый.
    "field_ink": "#fbf6ef",
    "field_dim": "rgba(251, 246, 239, 0.74)",
    "field_faint": "rgba(251, 246, 239, 0.45)",
    "field_wash": "rgba(255, 255, 255, 0.12)",
    "field_fill": "rgba(251, 246, 239, 0.5)",  # пустой кружок отметки на поле: 3:1 к кобальту
    "field_ok": "#8fe3b3",
    "field_warn": "#ffcf6b",
    "field_bad": "#ffb2a1",
    "ok": "#2f8a5c",
    "warn": "#b87a12",
    "bad": "#b23a24",         # единственный тревожный цвет: только для сбоев
}
# Жидкий градиент поля в цветах рефа design-refs/field-blue-glow.png: кобальт, фиолетовый,
# слива, роза и коралл перетекают мягкими пятнами. Пятно — (центр x, y, полуоси по ширине
# и высоте поля, поворот в градусах, цвет, непрозрачность в центре). Внизу слева — спокойный
# кобальт: там «Hi.» и список загрузок, светлому тексту нужен тёмный фон.
LIQUID_BASE = "#0b3cb0"
LIQUID = (
    (0.05, 0.02, 0.75, 0.45, 15, "#03318f", 0.9),
    (0.95, 0.04, 0.45, 0.30, 0, "#3a5bd0", 0.55),
    (0.30, 0.50, 0.70, 0.40, -25, "#4b4aa0", 0.85),
    (0.45, 0.30, 0.95, 0.11, 28, "#6a51a0", 0.6),
    (0.80, 0.30, 0.55, 0.38, 30, "#7c538e", 0.85),
    (0.62, 0.48, 0.30, 0.20, -20, "#b05c74", 0.7),
    (0.88, 0.62, 0.45, 0.30, 40, "#e2655f", 0.95),
    (0.15, 0.95, 0.70, 0.30, -5, "#023eb6", 0.95),
    (0.62, 0.74, 0.60, 0.09, -16, "#d8636a", 0.5),
    (0.95, 0.98, 0.40, 0.25, 0, "#5e4f94", 0.6),
)

# Глифы Segoe Fluent Icons / Segoe MDL2 Assets — коды у них общие.
GLYPH = {
    "settings": chr(0xE713),
    "cancel": chr(0xE711),
    "retry": chr(0xE72C),
    "folder": chr(0xE838),
    "arrow": chr(0xE72A),
    "video": chr(0xE714),
    "audio": chr(0xEC4F),
    "playlist": chr(0xE8FD),
}

_loaded_families = None
_noise = None


def load_fonts():
    """Регистрирует шрифты из assets/fonts (один раз) и возвращает имена их семейств."""
    global _loaded_families
    if _loaded_families is None:
        families = set()
        for path in sorted(FONTS.glob("*.ttf")):
            font_id = QFontDatabase.addApplicationFont(str(path))
            families.update(QFontDatabase.applicationFontFamilies(font_id))
        _loaded_families = frozenset(families)
    return _loaded_families


def icon_font_family():
    families = set(QFontDatabase.families())
    return next((name for name in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if name in families), SANS)


def prefer_grey_text(environ, platform=sys.platform):
    """До создания приложения: текст на Windows рисует FreeType, серым сглаживанием.

    DirectWrite и GDI рисуют ClearType даже с NoSubpixelAntialias — у светлых
    букв на синем поле остаётся синяя и оранжевая кайма. Явный выбор платформы не трогаем.
    """
    if platform == "win32":
        environ.setdefault("QT_QPA_PLATFORM", "windows:fontengine=freetype")


def smooth(font):
    """Серое сглаживание без хинтинга, как на Mac.

    Windows по умолчанию рисует текст ClearType: у светлых букв на тёмном
    появляется синяя и оранжевая кайма, а хинтинг подгоняет верхушки к сетке пикселей.
    """
    font.setStyleStrategy(QFont.StyleStrategy(QFont.PreferAntialias | QFont.NoSubpixelAntialias))
    font.setHintingPreference(QFont.PreferNoHinting)
    return font


def serif_font(size, italic=False):
    font = QFont(SERIF)
    font.setPixelSize(size)
    font.setItalic(italic)
    return smooth(font)


def tracking(size):
    """Трекинг Golos в процентах: текст чуть плотнее обычного, крупные цифры и заголовки — ещё плотнее.

    Проценты, а не пиксели: подписи с размером из стилей наследуют шрифт
    приложения, и сжатие масштабируется вместе с ними.
    """
    return 97 if size < 20 else 95.5 if size < 48 else 94


def sans_font(size, weight=QFont.Normal, tabular=False):
    font = QFont(SANS)
    font.setPixelSize(size)
    font.setWeight(weight)
    font.setLetterSpacing(QFont.PercentageSpacing, tracking(size))
    smooth(font)
    if tabular:
        # Моноширинные цифры: проценты и длительности не прыгают и встают в колонку.
        font.setFeature(QFont.Tag("tnum"), 1)
    return font


def figure_font(size):
    """Крупные цифры: Golos с самым плотным трекингом, чтобы число читалось одним знаком."""
    return sans_font(size, tabular=True)


def figure_html(number, tail="", size=None):
    """Крупное число с хвостом мельче, как «7:44 pm» на рефе: «39» и маленький «%»."""
    if not tail or size is None:
        return f"{number}{tail}"
    return f'{number}<span style="font-size:{round(size * 0.42)}px">{tail}</span>'


# Классы, которым Windows задаёт свой шрифт поверх шрифта приложения.
_FONT_CLASSES = ("QAbstractItemView", "QListView", "QListWidget", "QComboBox", "QMenu", "QMessageBox", "QTipLabel")


def apply(app):
    load_fonts()
    font = sans_font(14)
    app.setFont(font)
    palette = QPalette()
    for role, color in (
        (QPalette.Window, C["panel"]),
        (QPalette.WindowText, C["ink"]),
        (QPalette.Base, C["fill"]),
        (QPalette.AlternateBase, C["panel"]),
        (QPalette.Text, C["ink"]),
        (QPalette.Button, C["fill"]),
        (QPalette.ButtonText, C["ink"]),
        (QPalette.Highlight, C["lime"]),
        (QPalette.HighlightedText, C["ink"]),
        (QPalette.ToolTipBase, C["ink"]),
        (QPalette.ToolTipText, C["on_ink"]),
        (QPalette.PlaceholderText, C["placeholder"]),
    ):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet(stylesheet())
    # После стилей: установка таблицы стилей заново раздаёт классам системные шрифты.
    for name in _FONT_CLASSES:
        app.setFont(font, name)


def repolish(widget):
    """Перечитать стиль после смены динамического свойства (kind, role, state, off)."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def apply_title_bar(widget):
    """Рамка окна в цвет панели: светлая, без системной синевы."""
    if sys.platform != "win32":
        return
    try:
        hwnd = int(widget.winId())
        dwm = ctypes.windll.dwmapi
        dark = ctypes.c_int(0)
        dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark))
        panel = QColor(C["panel"])
        caption = ctypes.c_int(panel.red() | (panel.green() << 8) | (panel.blue() << 16))
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption), ctypes.sizeof(caption))
    except (AttributeError, OSError):
        pass


def noise_tile():
    """Плитка шума для плёночного зерна; рисуется режимом «перекрытие»."""
    global _noise
    if _noise is None:
        size = 180
        image = QImage(os.urandom(size * size), size, size, size, QImage.Format_Grayscale8).copy()
        _noise = QPixmap.fromImage(image)
    return _noise


_grain_tiles = {}
_field_layers = {}


def paint_grain(painter, rect, opacity):
    # Точка шума — пиксель экрана, а не логический: при масштабе 125% логический растянулся бы в пятна.
    ratio = painter.device().devicePixelRatioF() or 1.0
    tile = _grain_tiles.get(ratio)
    if tile is None:
        tile = QPixmap(noise_tile())
        tile.setDevicePixelRatio(ratio)
        _grain_tiles[ratio] = tile
    painter.save()
    painter.setOpacity(opacity)
    painter.setCompositionMode(QPainter.CompositionMode_Overlay)
    painter.drawTiledPixmap(rect, tile)
    painter.restore()


def mix(first, second, amount):
    """Цвет между first и second: amount=0 — first, amount=1 — second."""
    a, b = QColor(first), QColor(second)
    return QColor.fromRgbF(*(x + (y - x) * amount for x, y in zip(a.getRgbF()[:3], b.getRgbF()[:3])))


def paint_liquid(painter, width, height):
    """Жидкий градиент в прямоугольник 0, 0, width, height — для поля и для иконки."""
    painter.fillRect(QRectF(0, 0, width, height), QColor(LIQUID_BASE))
    for x, y, rx, ry, angle, color, alpha in LIQUID:
        # Пятно — круговой градиент, растянутый в эллипс и повёрнутый; край гаснет плавно, как капля краски.
        blob = QRadialGradient(QPointF(0, 0), 1.0)
        for stop, share in ((0.0, 1.0), (0.25, 0.85), (0.5, 0.5), (0.75, 0.18), (1.0, 0.0)):
            shade = QColor(color)
            shade.setAlphaF(alpha * share)
            blob.setColorAt(stop, shade)
        brush = QBrush(blob)
        brush.setTransform(QTransform().translate(x * width, y * height).rotate(angle).scale(rx * width, ry * height))
        painter.fillRect(QRectF(0, 0, width, height), brush)


def field_layer(width, height, ratio):
    """Жидкий градиент нужного размера; рисуется один раз на размер окна и берётся из кэша."""
    key = (width, height, ratio)
    layer = _field_layers.get(key)
    if layer is None:
        if len(_field_layers) > 8:
            _field_layers.clear()
        layer = QPixmap(max(int(width * ratio), 1), max(int(height * ratio), 1))
        layer.setDevicePixelRatio(ratio)
        layer.fill(Qt.transparent)
        painter = QPainter(layer)
        painter.setRenderHint(QPainter.Antialiasing)
        paint_liquid(painter, width, height)
        painter.end()
        _field_layers[key] = layer
    return layer


def paint_field(painter, rect):
    """Зернистое поле: жидкий градиент и мелкое плёночное зерно поверх."""
    rect = QRect(rect)
    ratio = painter.device().devicePixelRatioF() or 1.0
    painter.drawPixmap(rect.topLeft(), field_layer(rect.width(), rect.height(), ratio))
    paint_grain(painter, rect, 0.12)


def stylesheet():
    chevron = (ASSETS / "chevron.svg").as_posix()
    check = (ASSETS / "check.svg").as_posix()
    check_ink = (ASSETS / "check-ink.svg").as_posix()
    return f"""
QDialog, QMessageBox {{ background: {C['panel']}; }}
QWidget#strip, QWidget#stagePage, QWidget#downloads {{ background: transparent; }}
QLabel {{ background: transparent; color: {C['ink']}; }}
QLabel[role="title"] {{ font-size: 16px; font-weight: 600; }}
QLabel[role="caption"] {{ color: {C['ink_dim']}; font-size: 13px; }}
QLabel[role="dim"] {{ color: {C['ink_dim']}; }}
QLabel[role="small"] {{ color: {C['ink_dim']}; font-size: 12px; }}
QLabel[role="faint"] {{ color: {C['ink_faint']}; font-size: 12px; }}
QLabel[role="error"] {{ color: {C['bad']}; font-size: 12px; }}
QLabel[role="ok"] {{ color: {C['ok']}; font-size: 12px; }}
QLabel[role="warn"] {{ color: {C['warn']}; font-size: 12px; }}

/* На поле: чернила разной плотности вместо серого. */
QLabel[role="rowTitle"] {{ font-size: 14px; font-weight: 500; }}
/* Всё на синем поле — светлым. Правила с #field сильнее общих, поэтому и роли повторены с ним. */
QWidget#field QLabel {{ color: {C['field_ink']}; }}
QWidget#field QLabel[role="fieldCaption"] {{ color: {C['field_dim']}; font-size: 13px; }}
QWidget#field QLabel[role="fieldDim"] {{ color: {C['field_dim']}; font-size: 13px; }}
QWidget#field QLabel[role="fieldSmall"] {{ color: {C['field_dim']}; font-size: 12px; }}
QWidget#field QLabel[role="fieldState"] {{ color: {C['field_ink']}; font-size: 12px; }}
QWidget#field QLabel[role="fieldFaint"] {{ color: {C['field_faint']}; font-size: 12px; }}
QWidget#field QLabel[role="fieldError"] {{ color: {C['field_bad']}; font-size: 13px; }}
QWidget#field QLabel#netText {{ color: {C['field_ink']}; font-size: 12px; }}

QLabel#dot {{ border-radius: 3px; background: {C['field_faint']}; }}
QLabel#dot[state="running"] {{ background: {C['ink']}; }}
QLabel#dot[state="done"] {{ background: {C['ok']}; }}
QLabel#dot[state="failed"] {{ background: {C['bad']}; }}
QLabel#dot[state="warn"] {{ background: {C['warn']}; }}
QWidget#field QLabel#dot {{ background: {C['field_faint']}; }}
QWidget#field QLabel#dot[state="running"] {{ background: {C['field_ink']}; }}
QWidget#field QLabel#dot[state="done"] {{ background: {C['field_ok']}; }}
QWidget#field QLabel#dot[state="failed"] {{ background: {C['field_bad']}; }}
QWidget#field QLabel#dot[state="warn"] {{ background: {C['field_warn']}; }}

/* Радиус пилюль — ровно половина высоты: если больше, Qt рисует квадрат.
   Обычные поля и кнопки — 36 px и радиус 18; у пилюль с другой высотой она задана в коде. */
QFrame#linkBox {{ background: {C['fill']}; border: none; border-radius: 24px; }}
QLineEdit {{
    background: {C['fill']};
    border: none;
    border-radius: 18px;
    min-height: 36px;
    padding: 0 14px;
    color: {C['ink']};
    /* Иначе Qt берёт подсказку из цвета текста с половинной прозрачностью: 3,3:1 вместо 4,5:1. */
    placeholder-text-color: {C['placeholder']};
    selection-background-color: {C['lime']};
    selection-color: {C['ink']};
}}
QLineEdit:hover {{ background: {C['fill_hi']}; }}
QLineEdit:focus {{ background: {C['card']}; }}
QLineEdit:disabled {{ color: {C['ink_faint']}; }}
QLineEdit[invalid="true"] {{ background: #f1dcd6; }}
QLineEdit#url, QLineEdit#url:hover, QLineEdit#url:focus {{
    background: transparent; border: none; font-size: 15px; padding: 0; min-height: 0;
}}

QPushButton {{
    background: {C['fill']};
    border: none;
    border-radius: 18px;
    min-height: 36px;
    padding: 0 20px;
    color: {C['ink']};
}}
QPushButton:hover {{ background: {C['fill_hi']}; }}
QPushButton:pressed {{ background: #cfcec6; }}
QPushButton:disabled {{ color: {C['ink_faint']}; }}
QPushButton[kind="inset"] {{
    background: {C['card']};
    border-radius: 18px;
    min-height: 36px;
    max-height: 36px;
    padding: 0 16px;
    color: {C['ink']};
}}
QPushButton[kind="inset"]:hover {{ background: #ffffff; }}
QPushButton[kind="dark"] {{
    background: {C['ink']};
    padding: 0 24px;
    color: {C['on_ink']};
    font-weight: 500;
}}
QPushButton[kind="dark"]:hover {{ background: #2a2a25; }}
/* Главная кнопка: чёрная пилюля, стрелка — в своём вложенном кружке. */
QPushButton[kind="primary"] {{ background: {C['ink']}; border-radius: 26px; padding: 0; min-height: 52px; }}
QPushButton[kind="primary"]:hover {{ background: #2a2a25; }}
QPushButton[kind="primary"]:pressed {{ background: #000000; }}
QPushButton[kind="primary"]:disabled {{ background: {C['fill']}; }}
QLabel#ctaText {{ color: {C['on_ink']}; font-size: 15px; font-weight: 500; }}
QLabel#ctaText[off="true"] {{ color: {C['ink_faint']}; }}
QLabel#ctaIcon {{ background: rgba(255, 255, 255, 0.14); border-radius: 20px; }}
QLabel#ctaIcon[off="true"] {{ background: {C['fill_hi']}; }}
QPushButton[kind="link"] {{
    background: transparent;
    color: {C['ink_dim']};
    padding: 4px 6px;
    min-height: 20px;
    border-radius: 0;
}}
QPushButton[kind="link"]:hover {{ color: {C['ink']}; }}
QPushButton[kind="fieldLink"] {{
    background: transparent;
    color: {C['field_dim']};
    padding: 4px 6px;
    min-height: 20px;
    border-radius: 0;
}}
QPushButton[kind="fieldLink"]:hover {{ color: {C['field_ink']}; }}
QPushButton[kind="icon"] {{
    background: transparent;
    border-radius: 17px;
    padding: 0;
    min-width: 34px; max-width: 34px;
    min-height: 34px; max-height: 34px;
}}
QPushButton[kind="icon"]:hover {{ background: {C['fill']}; }}
QPushButton[kind="fieldIcon"] {{
    background: transparent;
    border-radius: 17px;
    padding: 0;
    min-width: 34px; max-width: 34px;
    min-height: 34px; max-height: 34px;
}}
QPushButton[kind="fieldIcon"]:hover {{ background: {C['field_wash']}; }}
QPushButton#netStatus {{ background: transparent; padding: 0; border-radius: 0; min-height: 0; }}

/* Пилюли качества: клавиши прибора. Выбранная — чернилами. */
QPushButton[kind="chip"] {{
    background: {C['fill']};
    border-radius: 16px;
    min-height: 32px;
    max-height: 32px;
    padding: 0 8px;
    color: {C['ink_soft']};
    font-size: 13px;
}}
QPushButton[kind="chip"]:hover {{ background: {C['fill_hi']}; color: {C['ink']}; }}
QPushButton[kind="chip"]:checked {{ background: {C['ink']}; color: {C['on_ink']}; }}

QFrame#segment {{ background: {C['fill']}; border: none; border-radius: 20px; }}
QPushButton[kind="segment"] {{
    background: transparent;
    border-radius: 16px;
    min-height: 32px;
    max-height: 32px;
    padding: 0 18px;
    color: {C['ink_dim']};
}}
QPushButton[kind="segment"]:hover {{ color: {C['ink']}; }}
QPushButton[kind="segment"]:checked {{ background: {C['ink']}; color: {C['on_ink']}; }}

QComboBox {{
    background: {C['fill']};
    border: none;
    border-radius: 18px;
    min-height: 36px;
    padding: 0 34px 0 18px;
    min-width: 150px;
    color: {C['ink']};
}}
QComboBox:hover {{ background: {C['fill_hi']}; }}
QComboBox:disabled {{ color: {C['ink_faint']}; }}
QComboBox::drop-down {{ border: none; width: 30px; subcontrol-origin: padding; subcontrol-position: center right; }}
QComboBox::down-arrow {{ image: url("{chevron}"); width: 11px; height: 11px; }}
QComboBox QAbstractItemView {{
    background: {C['card']};
    border: none;
    padding: 6px;
    outline: none;
    selection-background-color: {C['fill']};
    selection-color: {C['ink']};
}}
QComboBox QAbstractItemView::item {{ min-height: 30px; padding: 0 10px; }}

QCheckBox, QRadioButton {{ spacing: 10px; background: transparent; color: {C['ink']}; }}
QCheckBox:disabled, QRadioButton:disabled {{ color: {C['ink_faint']}; }}
QCheckBox::indicator, QListWidget::indicator {{
    width: 18px;
    height: 18px;
    border: none;
    border-radius: 9px;
    background: {C['off']};
}}
QCheckBox::indicator:hover {{ background: #6b6964; }}
QCheckBox::indicator:checked, QListWidget::indicator:checked {{
    background: {C['ink']};
    image: url("{check}");
}}
QCheckBox::indicator:disabled {{ background: {C['fill']}; }}
QCheckBox#onField {{ color: {C['field_ink']}; }}
QCheckBox#onField::indicator, QListWidget::indicator {{ background: {C['field_fill']}; }}
QCheckBox#onField::indicator:checked, QListWidget::indicator:checked {{
    background: {C['field_ink']};
    image: url("{check_ink}");
}}
QRadioButton::indicator {{
    width: 18px;
    height: 18px;
    border: none;
    border-radius: 9px;
    background: {C['off']};
}}
QRadioButton::indicator:hover {{ background: #6b6964; }}
QRadioButton::indicator:disabled {{ background: {C['fill']}; }}
QRadioButton::indicator:checked {{
    background: qradialgradient(cx: 0.5, cy: 0.5, radius: 0.5, fx: 0.5, fy: 0.5,
        stop: 0 {C['on_ink']}, stop: 0.3 {C['on_ink']}, stop: 0.38 {C['ink']}, stop: 1 {C['ink']});
}}

/* На поле полоса — чернилами: градиентом теперь залито само поле. */
QProgressBar {{
    background: rgba(255, 255, 255, 0.2);
    border: none;
    border-radius: 1px;
    min-height: 3px;
    max-height: 3px;
}}
QProgressBar::chunk {{ border-radius: 1px; background: {C['field_ink']}; }}

QScrollArea, QScrollArea > QWidget#qt_scrollarea_viewport, QWidget#scrollBody {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: rgba(15, 15, 13, 0.18); border-radius: 2px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: rgba(15, 15, 13, 0.32); }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: rgba(15, 15, 13, 0.18); border-radius: 2px; min-width: 30px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}
QWidget#field QScrollBar::handle:vertical {{ background: rgba(255, 255, 255, 0.3); }}
QWidget#field QScrollBar::handle:vertical:hover {{ background: rgba(255, 255, 255, 0.5); }}

QListWidget {{ background: transparent; border: none; padding: 0; outline: none; }}
QListWidget::item {{ padding: 5px 6px; border-radius: 10px; color: {C['field_ink']}; }}
QListWidget::item:hover, QListWidget::item:selected {{ background: {C['field_wash']}; color: {C['field_ink']}; }}

QToolTip {{
    background: {C['ink']};
    color: {C['on_ink']};
    border: none;
    padding: 6px 10px;
}}
"""
