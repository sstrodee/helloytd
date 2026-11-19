"""Виджеты: подписи, превью, пилюли, зернистое поле и строка загрузки."""

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPainterPath, QPixmap, QTextLayout
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .jobs import CANCELLED, DONE, FAILED, QUEUED, RUNNING
from .progress import describe_detail


def label(text="", role=None, parent=None):
    widget = QLabel(text, parent)
    widget.setTextFormat(Qt.PlainText)
    if role:
        widget.setProperty("role", role)
    return widget


def set_role(widget, role):
    if widget.property("role") != role:
        widget.setProperty("role", role)
        theme.repolish(widget)


class ElidedLabel(QLabel):
    """Однострочная подпись, которая не распирает окно, а сокращается с «…»."""

    def __init__(self, text="", role=None, elide=Qt.ElideRight, parent=None):
        super().__init__(text, parent)
        self._elide = elide
        if role:
            self.setProperty("role", role)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(40)

    def setText(self, text):
        super().setText(text)
        self._update_tooltip()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_tooltip()

    def _update_tooltip(self):
        self.setToolTip(self.text() if self.fontMetrics().horizontalAdvance(self.text()) > self.width() else "")

    def paintEvent(self, event):
        painter = QPainter(self)
        rect = self.contentsRect()
        text = self.fontMetrics().elidedText(self.text(), self._elide, rect.width())
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.drawText(rect, int(self.alignment() | Qt.TextSingleLine), text)


class ClampedLabel(QLabel):
    """Подпись в несколько строк: текст переносится, лишнее — «…» в последней строке."""

    def __init__(self, text="", role=None, lines=2, parent=None):
        super().__init__(text, parent)
        self._max_lines = lines
        if role:
            self.setProperty("role", role)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def setText(self, text):
        super().setText(text)
        self.updateGeometry()
        self.update()

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return len(self.visible_lines(width)) * self.fontMetrics().lineSpacing()

    def sizeHint(self):
        return QSize(super().sizeHint().width(), self.heightForWidth(max(self.width(), 1)))

    def visible_lines(self, width):
        """Строки, как они встанут в ширину; лишнее — «…» в последней видимой."""
        lines = []
        for paragraph in self.text().splitlines() or [""]:
            layout = QTextLayout(paragraph, self.font())
            layout.beginLayout()
            wrapped = []
            while True:
                line = layout.createLine()
                if not line.isValid():
                    break
                line.setLineWidth(width)
                wrapped.append(paragraph[line.textStart():line.textStart() + line.textLength()].rstrip())
            layout.endLayout()
            lines.extend(wrapped or [""])
        if len(lines) > self._max_lines:
            rest = " ".join(lines[self._max_lines - 1:])
            last = self.fontMetrics().elidedText(rest, Qt.ElideRight, width)
            lines = lines[:self._max_lines - 1] + [last]
        return lines

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(self.palette().color(self.foregroundRole()))
        step = self.fontMetrics().lineSpacing()
        rect = self.contentsRect()
        for index, line in enumerate(self.visible_lines(rect.width())):
            painter.drawText(QRectF(rect.left(), rect.top() + index * step, rect.width(), step),
                             int(Qt.AlignLeft | Qt.AlignVCenter | Qt.TextSingleLine), line)


class Thumbnail(QLabel):
    """Превью со скруглёнными углами; пока картинки нет — значок на полупрозрачной подложке."""

    def __init__(self, width, height, radius=10, parent=None):
        super().__init__(parent)
        self._radius = radius
        self._data = None
        self._glyph = theme.GLYPH["video"]
        self.setFixedSize(width, height)
        self.set_image(None)

    def resize_to(self, width, height):
        if (width, height) != (self.width(), self.height()):
            self.setFixedSize(width, height)
            self.set_image(self._data, self._glyph)

    def set_image(self, data, glyph=theme.GLYPH["video"]):
        self._data, self._glyph = data, glyph
        width, height = self.width(), self.height()
        ratio = self.devicePixelRatioF() or 1.0
        canvas = QPixmap(int(width * ratio), int(height * ratio))
        canvas.setDevicePixelRatio(ratio)
        canvas.fill(Qt.transparent)

        painter = QPainter(canvas)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        shape = QPainterPath()
        shape.addRoundedRect(QRectF(0, 0, width, height), self._radius, self._radius)
        painter.setClipPath(shape)

        image = QPixmap()
        if data and image.loadFromData(data):
            # Заполняем рамку целиком, обрезая лишнее по краям, как обложки на YouTube.
            scaled = image.scaled(int(width * ratio), int(height * ratio),
                                  Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            scaled.setDevicePixelRatio(ratio)
            offset = QPointF((scaled.width() / ratio - width) / 2, (scaled.height() / ratio - height) / 2)
            painter.drawPixmap(-offset, scaled)
        else:
            painter.fillPath(shape, QColor(255, 255, 255, 102))
            size = 22 if height > 80 else 16
            painter.drawPixmap(
                QRectF(width / 2 - size / 2, height / 2 - size / 2, size, size).toRect(),
                glyph_pixmap(glyph, theme.C["ink_soft"], size),
            )
        painter.end()
        self.setPixmap(canvas)


def glyph_pixmap(glyph, color, size=14):
    """Значок из шрифта в картинке с прозрачным фоном.

    Текстом тонкий глиф получает субпиксельное сглаживание ClearType — цветную
    кайму. На прозрачной картинке сглаживание только серое.
    """
    ratio = 3.0  # с запасом под любой масштаб экрана
    pixmap = QPixmap(int(size * ratio), int(size * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
    font = QFont(theme.icon_font_family())
    font.setPixelSize(size)
    painter.setFont(font)
    painter.setPen(QColor(color))
    painter.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, glyph)
    painter.end()
    return pixmap


def glyph_icon(glyph, color, size=14):
    return QIcon(glyph_pixmap(glyph, color, size))


class IconButton(QPushButton):
    def __init__(self, glyph, tooltip, color=None, on_field=False, parent=None):
        super().__init__(parent)
        self.setProperty("kind", "fieldIcon" if on_field else "icon")
        self.setIcon(glyph_icon(glyph, color or (theme.C["field_ink"] if on_field else theme.C["ink_dim"]), 15))
        self.setIconSize(QSize(15, 15))
        self.setToolTip(tooltip)
        self.setAccessibleName(tooltip)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)


class SegmentedControl(QFrame):
    """Переключатель на всю ширину: заливка-дорожка, выбранное — чернилами."""

    changed = Signal(str)

    def __init__(self, options, parent=None):
        super().__init__(parent)
        self.setObjectName("segment")
        self.setFixedHeight(40)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        self._group = QButtonGroup(self)
        self._buttons = {}
        for key, text in options:
            button = QPushButton(text)
            button.setCheckable(True)
            button.setProperty("kind", "segment")
            button.setCursor(Qt.PointingHandCursor)
            button.setFixedHeight(32)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            button.clicked.connect(lambda _checked=False, key=key: self.changed.emit(key))
            self._group.addButton(button)
            self._buttons[key] = button
            layout.addWidget(button)

    def value(self):
        return next(key for key, button in self._buttons.items() if button.isChecked())

    def set_value(self, key):
        self._buttons[key].setChecked(True)


class ChoiceGrid(QWidget):
    """Пилюли-варианты сеткой, как клавиши на приборе; выбрана всегда ровно одна."""

    changed = Signal(object)
    _CHIP_HEIGHT = 32

    def __init__(self, parent=None):
        super().__init__(parent)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(6)
        self._group = QButtonGroup(self)
        self._values = []
        self._columns = 0

    def buttons(self):
        return [self._group.button(index) for index in range(len(self._values))]

    def set_choices(self, choices, value, columns):
        """choices — [(значение, подпись, подсказка)]; нет value среди них — выбирается первый."""
        for button in self._group.buttons():
            self._group.removeButton(button)
            self._grid.removeWidget(button)
            button.hide()
            button.deleteLater()
        for column in range(self._columns):
            self._grid.setColumnStretch(column, 0)
        self._values = [choice for choice, _text, _tip in choices]
        self._columns = columns
        for index, (choice, text, tip) in enumerate(choices):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setProperty("kind", "chip")
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(tip)
            button.setFixedHeight(self._CHIP_HEIGHT)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            button.clicked.connect(lambda _checked=False, choice=choice: self.changed.emit(choice))
            self._group.addButton(button, index)
            self._grid.addWidget(button, index // columns, index % columns)
        for column in range(columns):
            self._grid.setColumnStretch(column, 1)
        rows = (len(choices) + columns - 1) // columns
        self.setFixedHeight(rows * self._CHIP_HEIGHT + max(0, rows - 1) * self._grid.verticalSpacing())
        self.set_value(value)

    def value(self):
        index = self._group.checkedId()
        return self._values[index] if index >= 0 else None

    def set_value(self, value):
        if self._values:
            index = self._values.index(value) if value in self._values else 0
            self._group.button(index).setChecked(True)


class Field(QWidget):
    """Зернистое поле с жидким градиентом: на нём всё, что сейчас важно."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("field")  # по этому имени стили красят всё на поле светлым

    def paintEvent(self, event):
        painter = QPainter(self)
        theme.paint_field(painter, self.rect())


class PillButton(QPushButton):
    """Чёрная кнопка-пилюля; стрелка живёт в своём вложенном кружке у правого края."""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self.setProperty("kind", "primary")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(52)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 6, 6, 6)
        layout.setSpacing(16)
        self._text = QLabel(text)
        self._text.setTextFormat(Qt.PlainText)
        self.setAccessibleName(text)
        self._text.setObjectName("ctaText")
        self._arrow = QLabel()
        self._arrow.setObjectName("ctaIcon")
        self._arrow.setFixedSize(40, 40)
        self._arrow.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._text, 1)
        layout.addWidget(self._arrow)
        for child in (self._text, self._arrow):
            child.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._sync()

    def setText(self, text):
        self._text.setText(text)
        self.setAccessibleName(text)
        self._sync()

    def text(self):
        return self._text.text()

    def sizeHint(self):
        return self.layout().sizeHint()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.EnabledChange:
            self._sync()

    def _sync(self):
        off = not self.isEnabled()
        for child in (self._text, self._arrow):
            child.setProperty("off", off)
            theme.repolish(child)
        color = theme.C["ink_faint"] if off else theme.C["on_ink"]
        self._arrow.setPixmap(glyph_pixmap(theme.GLYPH["arrow"], color, 14))


class PlaylistDelegate(QStyledItemDelegate):
    """Строка плейлиста: отметка и название слева, длительность — своей колонкой справа, моноширинными цифрами."""

    DURATION = Qt.UserRole + 1
    GAP = 18

    def __init__(self, parent=None):
        super().__init__(parent)
        self._font = theme.sans_font(13, tabular=True)
        self._column = QFontMetrics(self._font).horizontalAdvance("0:00:00")

    def paint(self, painter, option, index):
        duration = index.data(self.DURATION) or ""
        item = QStyleOptionViewItem(option)
        self.initStyleOption(item, index)
        widget = item.widget
        style = widget.style() if widget is not None else None
        text_rect = style.subElementRect(QStyle.SE_ItemViewItemText, item, widget)
        reserve = self._column + self.GAP if duration else 0
        # Название сокращается заранее, чтобы не заехать на колонку длительности.
        item.text = item.fontMetrics.elidedText(item.text, Qt.ElideRight, max(text_rect.width() - reserve, 20))
        style.drawControl(QStyle.CE_ItemViewItem, item, painter, widget)
        if duration:
            painter.save()
            painter.setFont(self._font)
            painter.setPen(QColor(251, 246, 239, 189))
            painter.drawText(text_rect, int(Qt.AlignRight | Qt.AlignVCenter), duration)
            painter.restore()


class StatusDot(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dot")
        self.setFixedSize(7, 7)

    def set_state(self, state):
        if self.property("state") != state:
            self.setProperty("state", state)
            theme.repolish(self)


class JobRow(QFrame):
    """Строка загрузки прямо на поле: превью, название, состояние и подробности отдельными словами."""

    cancel_requested = Signal(object)
    retry_requested = Signal(object)
    reveal_requested = Signal(object)

    STATES = {RUNNING: "скачивается", QUEUED: "в очереди", DONE: "готово", FAILED: "ошибка", CANCELLED: "отменено"}

    def __init__(self, job, parent=None):
        super().__init__(parent)
        self.job = job
        self.setObjectName("jobRow")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(16)

        self.thumb = Thumbnail(72, 41, radius=8)
        glyph = theme.GLYPH["audio"] if job.kind == "audio" else theme.GLYPH["video"]
        self.thumb.set_image(job.thumbnail, glyph)
        layout.addWidget(self.thumb, 0, Qt.AlignVCenter)

        middle = QVBoxLayout()
        middle.setSpacing(5)
        middle.setContentsMargins(0, 0, 0, 0)
        self.title = ElidedLabel(job.title, role="rowTitle")
        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        self.dot = StatusDot()
        self.state = label("", "fieldState")
        self.status = ElidedLabel("", role="fieldSmall")
        status_row.addWidget(self.dot, 0, Qt.AlignVCenter)
        status_row.addWidget(self.state)
        status_row.addSpacing(4)
        status_row.addWidget(self.status, 1)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 1000)
        middle.addWidget(self.title)
        middle.addLayout(status_row)
        middle.addWidget(self.bar)
        layout.addLayout(middle, 1)

        self._on_stage = False
        self.figure = QLabel("")
        self.figure.setFont(theme.figure_font(22))
        self.figure.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.figure.setMinimumWidth(64)
        layout.addWidget(self.figure)

        self.cancel_button = IconButton(theme.GLYPH["cancel"], "Отменить", on_field=True)
        self.retry_button = IconButton(theme.GLYPH["retry"], "Повторить", on_field=True)
        self.reveal_button = IconButton(theme.GLYPH["folder"], "Показать в папке", on_field=True)
        self.cancel_button.clicked.connect(lambda: self.cancel_requested.emit(self.job))
        self.retry_button.clicked.connect(lambda: self.retry_requested.emit(self.job))
        self.reveal_button.clicked.connect(lambda: self.reveal_requested.emit(self.job))
        for button in (self.reveal_button, self.retry_button, self.cancel_button):
            layout.addWidget(button, 0, Qt.AlignVCenter)

        self.refresh()

    def set_on_stage(self, on_stage):
        """Загрузка показана крупно на поле — строка не повторяет её цифры, только название и состояние."""
        if on_stage != self._on_stage:
            self._on_stage = on_stage
            self.refresh()

    def refresh(self):
        job = self.job
        state = job.state
        figure = ""
        detail = job.detail

        if state == RUNNING:
            progress = job.progress
            if progress is not None and progress.fraction is not None:
                self.bar.setRange(0, 1000)
                self.bar.setValue(int(progress.fraction * 1000))
                figure = f"{progress.fraction * 100:.0f}%"
            else:
                self.bar.setRange(0, 0)  # бегущая полоса, пока размер неизвестен
            detail = describe_detail(progress)
        elif state == DONE and job.message:
            detail = job.message
        elif state == FAILED:
            detail = job.message or "Не получилось скачать"

        quiet = self._on_stage and state == RUNNING
        if quiet:
            figure, detail = "", ""
        self.state.setText(self.STATES[state])
        self.status.setText(detail)
        set_role(self.status, "fieldError" if state == FAILED else "fieldSmall")
        self.dot.set_state({RUNNING: "running", DONE: "done", FAILED: "failed"}.get(state, "idle"))
        self.figure.setText(figure)
        self.figure.setVisible(bool(figure))
        self.bar.setVisible(state == RUNNING and not quiet)
        self.cancel_button.setVisible(state in (RUNNING, QUEUED))
        self.retry_button.setVisible(state in (FAILED, CANCELLED) and job.request is not None)
        self.reveal_button.setVisible(state == DONE and bool(job.path))
