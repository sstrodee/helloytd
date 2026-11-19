"""Настройки: маршрут до YouTube, cookies и компоненты (yt-dlp, ffmpeg, JS-движок)."""

import re
import sys

from PySide6.QtCore import QProcess, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from yt_dlp.version import __version__ as YTDLP_VERSION

from . import theme
from .i18n import tr
from .links import redact_url_credentials
from .widgets import label

BROWSERS = (
    ("firefox", "Firefox"),
    ("chrome", "Chrome"),
    ("edge", "Edge"),
    ("brave", "Brave"),
    ("opera", "Opera"),
    ("vivaldi", "Vivaldi"),
    ("chromium", "Chromium"),
)
COOKIE_MODES = (
    ("auto", "только если YouTube попросит войти"),
    ("always", "всегда"),
    ("never", "никогда"),
)


class SettingsDialog(QDialog):
    def __init__(self, settings, env, parent=None, *, allow_update=True):
        super().__init__(parent)
        self.setWindowTitle(tr("Настройки"))
        self.setMinimumWidth(560)
        self._settings = dict(settings)
        self._env = env
        self._process = None

        frame = QVBoxLayout(self)
        frame.setContentsMargins(24, 22, 24, 22)
        frame.setSpacing(12)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFocusPolicy(Qt.NoFocus)
        content = QWidget()
        content.setObjectName("scrollBody")
        scroll.setWidget(content)
        frame.addWidget(scroll, 1)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.resize(600, min(760, self.screen().availableGeometry().height() - 64))

        layout.addWidget(label(tr("Язык"), "title"))
        self.language_combo = self._combo(
            (("auto", "системный"), ("en", "English"), ("ru", "Русский")),
            self._settings.get("language", "auto"),
        )
        self.language_combo.setAccessibleName(tr("Язык"))
        language_row = QHBoxLayout()
        language_row.addWidget(self.language_combo)
        language_row.addWidget(self._wrapped(tr("Язык применяется после перезапуска."), "small"), 1)
        layout.addLayout(language_row)
        layout.addSpacing(24)

        layout.addWidget(label(tr("Сеть"), "title"))
        layout.addWidget(self._wrapped(
            tr("Когда YouTube открывается только через VPN, его прокси находится автоматически."), "dim"))
        self.route_group = QButtonGroup(self)
        self.route_auto = QRadioButton(tr("автоматически (рекомендуется)"))
        self.route_direct = QRadioButton(tr("напрямую, без прокси"))
        self.route_manual = QRadioButton(tr("через прокси"))
        self.proxy_edit = QLineEdit(self._settings["manual_proxy"])
        self.proxy_edit.setPlaceholderText("http://127.0.0.1:10809")
        for button, key in ((self.route_auto, "auto"), (self.route_direct, "direct"), (self.route_manual, "manual")):
            self.route_group.addButton(button)
            button.setChecked(self._settings["route_mode"] == key)
            button.toggled.connect(self._sync_proxy_field)
        layout.addWidget(self.route_auto)
        layout.addWidget(self.route_direct)
        manual_row = QHBoxLayout()
        manual_row.addWidget(self.route_manual)
        manual_row.addWidget(self.proxy_edit, 1)
        layout.addLayout(manual_row)
        layout.addWidget(self._wrapped(self._route_summary(), "small"))
        self._sync_proxy_field()

        layout.addSpacing(24)

        layout.addWidget(label(tr("Вход в YouTube"), "title"))
        layout.addWidget(self._wrapped(
            tr("Нужен для видео 18+, приватных видео и проверки на бота. "
            "Cookies берутся из браузера, в котором выполнен вход в YouTube."), "dim"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        self.browser_combo = self._combo(BROWSERS, self._settings["cookies_browser"])
        self.cookie_mode_combo = self._combo(COOKIE_MODES, self._settings["cookies_mode"])
        grid.addWidget(label(tr("браузер"), "dim"), 0, 0)
        grid.addWidget(self.browser_combo, 0, 1)
        grid.addWidget(label(tr("когда брать"), "dim"), 1, 0)
        grid.addWidget(self.cookie_mode_combo, 1, 1)
        grid.setColumnStretch(2, 1)
        layout.addLayout(grid)
        layout.addWidget(self._wrapped(
            tr("Chrome и Edge шифруют cookies, и прочитать их часто не выходит. С Firefox надёжнее."), "small"))

        layout.addSpacing(24)

        layout.addWidget(label(tr("Компоненты"), "title"))
        ytdlp_row = QHBoxLayout()
        ytdlp_row.addWidget(label(f"yt-dlp {YTDLP_VERSION}", None))
        ytdlp_row.addStretch(1)
        self.update_status = label("", "small")
        ytdlp_row.addWidget(self.update_status)
        self.update_button = QPushButton(tr("обновить yt-dlp"))
        self.update_button.setCursor(Qt.PointingHandCursor)
        self.update_button.clicked.connect(self._update_ytdlp)
        self.update_button.setEnabled(allow_update)
        if not allow_update:
            self.update_button.setToolTip(tr("Обновление доступно после завершения сетевых задач."))
        ytdlp_row.addWidget(self.update_button)
        layout.addLayout(ytdlp_row)
        layout.addWidget(self._component_line(
            "ffmpeg", env.ffmpeg_dir,
            tr("не найден, без него не склеить 1080p+ и не сделать mp3. Установка: winget install Gyan.FFmpeg")))
        layout.addWidget(self._component_line(
            tr("JS-движок"), env.js_runtime[1] if env.js_runtime else None,
            tr("не найден, YouTube отдаст не все качества. Установка: winget install DenoLand.Deno")))

        layout.addStretch(1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton(tr("отмена"))
        cancel.clicked.connect(self.reject)
        done = QPushButton(tr("сохранить"))
        done.setProperty("kind", "dark")
        done.setDefault(True)
        done.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(done)
        frame.addLayout(buttons)

    def values(self):
        settings = dict(self._settings)
        settings["language"] = self.language_combo.currentData()
        settings["route_mode"] = (
            "direct" if self.route_direct.isChecked()
            else "manual" if self.route_manual.isChecked()
            else "auto"
        )
        settings["manual_proxy"] = self.proxy_edit.text().strip()
        settings["cookies_browser"] = self.browser_combo.currentData()
        settings["cookies_mode"] = self.cookie_mode_combo.currentData()
        return settings

    def showEvent(self, event):
        super().showEvent(event)
        theme.apply_title_bar(self)

    def _route_summary(self):
        env = self._env
        if env.reachable is None:
            return tr("сейчас: проверка сети…")
        if not env.reachable:
            return tr("сейчас: YouTube недоступен ни напрямую, ни через найденные прокси")
        return (tr("сейчас: через {proxy}", proxy=redact_url_credentials(env.proxy))
                if env.proxy else tr("сейчас: напрямую"))

    def _sync_proxy_field(self):
        self.proxy_edit.setEnabled(self.route_manual.isChecked())

    def _update_ytdlp(self):
        self.update_button.setEnabled(False)
        self.update_status.setText(tr("Обновление…"))
        # Без кэша pip: portable-программа не должна оставлять его в профиле.
        arguments = ["-m", "pip", "install", "--upgrade", "--disable-pip-version-check",
                     "--no-cache-dir", "yt-dlp[default]"]
        if self._env.proxy and self._env.proxy.startswith("http"):
            arguments += ["--proxy", self._env.proxy]
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.finished.connect(self._on_update_finished)
        self._process.errorOccurred.connect(self._on_update_error)
        self._process.start(sys.executable, arguments)

    def done(self, result):
        if self._process is not None and self._process.state() != QProcess.NotRunning:
            self.update_status.setText(tr("Установка пакета ещё идёт…"))
            return
        super().done(result)

    def _on_update_error(self, error):
        if error == QProcess.FailedToStart:
            self.update_button.setEnabled(True)
            self.update_status.setText(tr("Не удалось запустить обновление yt-dlp."))

    def _on_update_finished(self, exit_code, _status):
        output = bytes(self._process.readAll()).decode("utf-8", "replace")
        self.update_button.setEnabled(True)
        if exit_code != 0:
            last = next((line for line in reversed(output.splitlines()) if line.strip()), "")
            self.update_status.setText(tr("Не получилось: {error}", error=redact_url_credentials(last)[:80]))
            theme.repolish(self.update_status)
            return
        installed = re.search(r"Successfully installed .*?yt-dlp-([\w.]+)", output)
        if installed:
            self.update_status.setText(tr("Обновлено до {version}, заработает после перезапуска",
                                          version=installed.group(1)))
        else:
            self.update_status.setText(tr("Уже последняя версия"))

    @staticmethod
    def _combo(options, current):
        combo = QComboBox()
        for key, text in options:
            combo.addItem(tr(text), key)
        combo.setCurrentIndex(max(combo.findData(current), 0))
        return combo

    @staticmethod
    def _wrapped(text, role):
        widget = label(text, role)
        widget.setWordWrap(True)
        return widget

    @staticmethod
    def _component_line(name, found, missing_hint):
        if found:
            widget = label(tr("{name}: найден", name=name), "small")
            widget.setToolTip(found)
            return widget
        widget = label(f"{name}: {missing_hint}", "warn")
        widget.setWordWrap(True)
        widget.setTextInteractionFlags(Qt.TextSelectableByMouse)
        return widget
