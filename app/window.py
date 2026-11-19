"""Главное окно: слева панель-прибор со всеми настройками, справа зернистое поле с тем, что сейчас важно."""

import logging
import os
import subprocess
import time
from pathlib import Path

from PySide6.QtCore import QLocale, QStandardPaths, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .formats import QUALITY_TIERS, format_duration, parse_range, tier_name
from .i18n import language, tr, video_count, video_noun
from .jobs import CANCELLED, DONE, FAILED, QUEUED, RUNNING, Job, JobQueue
from .links import is_youtube_url, normalize_url, redact_url_credentials
from .options import AUDIO_CHOICES, FRAGMENT_MAX_HEIGHT, PLAYLIST_PREVIEW_LIMIT, DownloadRequest
from .progress import Progress, describe_detail
from .settings_dialog import SettingsDialog
from .storage import append_history, clear_history, load_history, load_settings, save_settings
from .widgets import (
    ChoiceGrid,
    ClampedLabel,
    ElidedLabel,
    Field,
    IconButton,
    JobRow,
    PillButton,
    PlaylistDelegate,
    SegmentedControl,
    StatusDot,
    Thumbnail,
    label,
    set_role,
)
from .workers import THUMBNAIL_LIMIT, DownloadWorker, Environment, EnvironmentProbe, InfoFetcher

log = logging.getLogger("ytdl")

APP_TITLE = "helloytd"
HISTORY_ROWS = 50
STRIP_WIDTH = 376
FFMPEG_HINT = (
    "Не найден ffmpeg: без него не склеить видео 1080p+ со звуком и не сделать mp3. "
    "Установка: winget install Gyan.FFmpeg"
)
JS_HINT = (
    "Не найден Node.js или Deno: YouTube отдаст не все качества. "
    "Установка: winget install DenoLand.Deno"
)
# Подписи на пилюлях формата звука; полные названия — в AUDIO_CHOICES.
AUDIO_CHIPS = {"mp3-320": "mp3 320", "mp3-192": "mp3 192", "m4a": "m4a"}


def default_out_dir():
    videos = QStandardPaths.writableLocation(QStandardPaths.MoviesLocation) or str(Path.home() / "Videos")
    return str(Path(videos) / "YouTube")


def reveal_in_explorer(path):
    path = os.path.normpath(path)
    if os.path.isfile(path):
        subprocess.Popen(f'explorer /select,"{path}"')
    elif os.path.isdir(path):
        os.startfile(path)
    elif os.path.isdir(os.path.dirname(path)):
        os.startfile(os.path.dirname(path))


def ask(parent, title, text):
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Question)
    box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    box.setDefaultButton(QMessageBox.No)
    box.button(QMessageBox.Yes).setText(tr("Да"))
    box.button(QMessageBox.No).setText(tr("Нет"))
    theme.apply_title_bar(box)
    return box.exec() == QMessageBox.Yes


def caption(text, on_field=False):
    """Подпись группы строчными буквами, как на приборе: «ссылка», «качество»."""
    return label(text, "fieldCaption" if on_field else "caption")


class NetStatus(QPushButton):
    """Состояние сети: точка и короткий текст; по клику сеть проверяется заново."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("netStatus")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(26)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(9)
        self._dot = StatusDot()
        self._text = QLabel("")
        self._text.setObjectName("netText")
        for child in (self._dot, self._text):
            child.setAttribute(Qt.WA_TransparentForMouseEvents)
            layout.addWidget(child, 0, Qt.AlignVCenter)

    def show_state(self, state, text, tooltip):
        self._dot.set_state(state)
        self._text.setText(text)
        self.setToolTip(tooltip)
        self.setMinimumWidth(self.layout().sizeHint().width())


class MainWindow(QWidget):
    def __init__(self, data_dir):
        super().__init__()
        self.setObjectName("root")
        self.setWindowTitle(APP_TITLE)
        self.setAcceptDrops(True)
        self.resize(1040, 740)
        self.setMinimumSize(960, 640)

        self._data_dir = Path(data_dir)
        self._settings_path = self._data_dir / "settings.json"
        self._history_path = self._data_dir / "history.json"
        self._thumbs_dir = self._data_dir / "thumbs"
        self.settings = load_settings(self._settings_path)
        if not self.settings["out_dir"]:
            self.settings["out_dir"] = default_out_dir()

        self.env = Environment()
        self.preview = None
        self.preview_thumb = None
        self.queue = JobQueue(self._start_worker)
        self._rows = {}
        self._threads = set()
        self._probe = None
        self._fetch_serial = 0
        self._fetch_url = None
        self._fetch_as_playlist = False
        self._pending_fetch = None
        self._preview_worker = None
        self._closing = False
        self._last_clipboard = None
        self._shown_once = False
        self._card_shown = False

        self._fetch_timer = QTimer(self)
        self._fetch_timer.setSingleShot(True)
        self._fetch_timer.setInterval(450)
        self._fetch_timer.timeout.connect(self._fetch_from_field)

        self._build()
        self._apply_settings()
        self._load_history()
        self._update_title()
        self._check_environment()
        QGuiApplication.instance().applicationStateChanged.connect(self._on_app_state)

    # ----- построение окна -------------------------------------------------

    def _build(self):
        # Как прибор neutone: узкая панель с ручками и большое зернистое поле до краёв окна.
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_strip())
        root.addWidget(self._build_field(), 1)

    def _build_strip(self):
        strip = QWidget()
        strip.setObjectName("strip")
        strip.setFixedWidth(STRIP_WIDTH)
        footer = QVBoxLayout(strip)
        footer.setContentsMargins(32, 22, 32, 28)
        footer.setSpacing(0)
        controls_scroll = QScrollArea()
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        controls_scroll.setFocusPolicy(Qt.NoFocus)
        controls = QWidget()
        controls.setObjectName("scrollBody")
        controls_scroll.setWidget(controls)
        footer.addWidget(controls_scroll, 1)
        layout = QVBoxLayout(controls)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top = QHBoxLayout()
        brand = QLabel(APP_TITLE)
        brand.setFont(theme.serif_font(26, italic=True))
        top.addWidget(brand, 0, Qt.AlignVCenter)
        top.addStretch(1)
        settings_button = IconButton(theme.GLYPH["settings"], tr("Настройки"), theme.C["ink"])
        settings_button.clicked.connect(self._open_settings)
        top.addWidget(settings_button, 0, Qt.AlignVCenter)
        footer.insertLayout(0, top)
        footer.insertSpacing(1, 30)

        layout.addWidget(caption(tr("ссылка")))
        layout.addSpacing(8)
        layout.addWidget(self._build_link())

        layout.addSpacing(28)
        self.mode_switch = SegmentedControl([("video", tr("видео")), ("audio", tr("аудио"))])
        self.mode_switch.changed.connect(self._on_mode_changed)
        layout.addWidget(self.mode_switch)

        layout.addSpacing(26)
        layout.addWidget(caption(tr("качество")))
        layout.addSpacing(8)
        self.quality = ChoiceGrid()
        self.quality.changed.connect(self._on_quality_changed)
        layout.addWidget(self.quality)

        layout.addSpacing(26)
        self.subs_check = QCheckBox(tr("субтитры (рус, англ)"))
        self.subs_check.toggled.connect(self._on_subtitles_toggled)
        layout.addWidget(self.subs_check)
        layout.addSpacing(12)
        self.trim_check = QCheckBox(tr("только фрагмент"))
        self.trim_check.toggled.connect(self._on_trim_toggled)
        layout.addWidget(self.trim_check)
        layout.addWidget(self._build_trim())
        self.trim_error = label("", "error")
        self.trim_error.setWordWrap(True)
        self.trim_error.hide()
        layout.addWidget(self.trim_error)

        layout.addStretch(1)
        layout = footer
        self.banner = QWidget()
        banner_layout = QHBoxLayout(self.banner)
        banner_layout.setContentsMargins(0, 0, 0, 18)
        banner_layout.setSpacing(10)
        banner_dot = StatusDot()
        banner_dot.set_state("warn")
        self.banner_text = label("", "warn")
        self.banner_text.setWordWrap(True)
        self.banner_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        banner_layout.addWidget(banner_dot, 0, Qt.AlignTop)
        banner_layout.addWidget(self.banner_text, 1)
        self.banner.hide()
        layout.addWidget(self.banner)

        layout.addWidget(caption(tr("папка")))
        layout.addSpacing(2)
        folder = QHBoxLayout()
        folder.setSpacing(4)
        self.folder_label = ElidedLabel("", "dim", Qt.ElideMiddle)
        folder.addWidget(self.folder_label, 1)
        change = QPushButton(tr("изменить"))
        change.setProperty("kind", "link")
        change.setCursor(Qt.PointingHandCursor)
        change.clicked.connect(self._choose_folder)
        folder.addWidget(change)
        open_folder = IconButton(theme.GLYPH["folder"], tr("Открыть папку"))
        open_folder.clicked.connect(self._open_folder)
        folder.addWidget(open_folder)
        layout.addLayout(folder)

        layout.addSpacing(18)
        self.download_button = PillButton(tr("скачать"))
        self.download_button.clicked.connect(self._start_download)
        layout.addWidget(self.download_button)
        return strip

    def _build_link(self):
        box = QFrame()
        box.setObjectName("linkBox")
        box.setFixedHeight(48)
        row = QHBoxLayout(box)
        row.setContentsMargins(18, 6, 6, 6)
        row.setSpacing(8)
        self.url_edit = QLineEdit()
        self.url_edit.setObjectName("url")
        self.url_edit.setPlaceholderText(tr("видео или плейлист"))
        self.url_edit.textEdited.connect(self._on_url_edited)
        self.url_edit.setAccessibleName(tr("ссылка на видео или плейлист"))
        self.url_edit.returnPressed.connect(self._on_url_enter)
        paste_button = QPushButton(tr("вставить"))
        paste_button.setProperty("kind", "inset")
        paste_button.setFixedHeight(36)
        paste_button.setCursor(Qt.PointingHandCursor)
        paste_button.clicked.connect(self._paste_from_clipboard)
        row.addWidget(self.url_edit, 1)
        row.addWidget(paste_button)
        return box

    def _build_trim(self):
        self.trim_fields = QWidget()
        layout = QHBoxLayout(self.trim_fields)
        layout.setContentsMargins(28, 12, 0, 0)
        layout.setSpacing(10)
        self.trim_start = QLineEdit()
        self.trim_start.setAccessibleName(tr("начало фрагмента"))
        self.trim_start.setPlaceholderText("0:00")
        self.trim_end = QLineEdit()
        self.trim_end.setAccessibleName(tr("конец фрагмента"))
        self.trim_end.setPlaceholderText(tr("конец"))
        layout.addWidget(label(tr("с"), "dim"))
        layout.addWidget(self.trim_start)
        layout.addWidget(label(tr("по"), "dim"))
        layout.addWidget(self.trim_end)
        layout.addStretch(1)
        for edit in (self.trim_start, self.trim_end):
            edit.setObjectName("trim")
            edit.setFixedWidth(84)
            edit.setAlignment(Qt.AlignCenter)
            edit.textEdited.connect(self._on_trim_edited)
        self.trim_fields.hide()
        return self.trim_fields

    def _build_field(self):
        self.field = Field()
        layout = QVBoxLayout(self.field)
        layout.setContentsMargins(48, 26, 40, 30)
        layout.setSpacing(0)

        top = QHBoxLayout()
        self.net_pill = NetStatus()
        self.net_pill.clicked.connect(self._check_environment)
        top.addWidget(self.net_pill)
        top.addStretch(1)
        layout.addLayout(top)
        layout.addSpacing(22)

        stage = QWidget()
        stage.setObjectName("stagePage")
        self.stage = QStackedLayout(stage)
        self.idle_page = self._build_idle()
        self.card_page = self._build_card()
        self.progress_page = self._build_progress()
        for page in (self.idle_page, self.card_page, self.progress_page):
            self.stage.addWidget(page)
        layout.addWidget(stage, 3)

        self.downloads = self._build_downloads()
        layout.addWidget(self.downloads, 2)
        return self.field

    def _build_idle(self):
        # В покое поле — это иконка: «Hi.» на градиенте.
        page = QWidget()
        page.setObjectName("stagePage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch(1)
        hello = QLabel("Hi.")
        hello.setFont(theme.serif_font(250))
        layout.addWidget(hello)
        return page

    def _build_card(self):
        # Что откроется по ссылке: превью, рядом крупная цифра, ниже название.
        page = QWidget()
        page.setObjectName("stagePage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top = QHBoxLayout()
        top.setSpacing(28)
        self.card_thumb = Thumbnail(256, 144, radius=14)
        top.addWidget(self.card_thumb, 0, Qt.AlignTop)
        figure = QVBoxLayout()
        figure.setSpacing(0)
        self.card_figure = QLabel("")
        self.card_figure.setFont(theme.figure_font(72))
        self.card_figure.setTextFormat(Qt.RichText)
        self.card_figure_unit = label("", "fieldDim")
        figure.addWidget(self.card_figure)
        figure.addWidget(self.card_figure_unit)
        figure.addStretch(1)
        top.addLayout(figure, 1)
        layout.addLayout(top)

        layout.addSpacing(22)
        self.card_title = ClampedLabel("", lines=2)
        self.card_title.setFont(theme.sans_font(24, QFont.Medium))
        layout.addWidget(self.card_title)
        layout.addSpacing(6)
        self.card_meta = ElidedLabel("", "fieldDim")
        layout.addWidget(self.card_meta)
        layout.addSpacing(12)
        self.card_status = label("", "fieldDim")
        self.card_status.setWordWrap(True)
        self.card_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.card_status)
        self.card_busy = QProgressBar()
        self.card_busy.setRange(0, 0)
        self.card_busy.setTextVisible(False)
        self.card_busy.setMaximumWidth(256)
        layout.addWidget(self.card_busy)
        self.whole_playlist = QCheckBox(tr("скачать весь плейлист"))
        self.whole_playlist.setObjectName("onField")
        self.whole_playlist.toggled.connect(self._on_whole_playlist_toggled)
        layout.addWidget(self.whole_playlist)

        self.playlist_box = QWidget()
        playlist_layout = QVBoxLayout(self.playlist_box)
        playlist_layout.setContentsMargins(0, 0, 0, 0)
        playlist_layout.setSpacing(4)
        bar = QHBoxLayout()
        self.playlist_count = label("", "fieldDim")
        bar.addWidget(self.playlist_count)
        bar.addStretch(1)
        for text, checked in ((tr("выбрать все"), True), (tr("снять все"), False)):
            button = QPushButton(text)
            button.setProperty("kind", "fieldLink")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, state=checked: self._check_all_entries(state))
            bar.addWidget(button)
        self.playlist_list = QListWidget()
        # Список занимает всё свободное место, но своей желаемой высотой не распирает окно:
        # из-за переноса заголовка Qt считает минимум окна по желаемым высотам.
        self.playlist_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        self.playlist_list.setMinimumHeight(110)
        self.playlist_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.playlist_list.setTextElideMode(Qt.ElideRight)
        self.playlist_list.setItemDelegate(PlaylistDelegate(self.playlist_list))
        self.playlist_list.itemChanged.connect(lambda _item: self._on_selection_changed())
        playlist_layout.addLayout(bar)
        playlist_layout.addWidget(self.playlist_list, 1)
        self.playlist_box.hide()
        layout.addWidget(self.playlist_box, 100)
        layout.addStretch(1)
        return page

    def _build_progress(self):
        # Пока идёт загрузка: огромный процент на поле, которое наполняется цветом снизу.
        page = QWidget()
        page.setObjectName("stagePage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.progress_figure = QLabel("")
        self.progress_figure.setFont(theme.figure_font(150))
        self.progress_figure.setTextFormat(Qt.RichText)
        layout.addWidget(self.progress_figure)
        self.progress_title = ClampedLabel("", lines=2)
        self.progress_title.setFont(theme.sans_font(20, QFont.Medium))
        layout.addWidget(self.progress_title)
        layout.addSpacing(8)
        self.progress_detail = ElidedLabel("", "fieldDim")
        layout.addWidget(self.progress_detail)
        layout.addSpacing(18)
        self.progress_busy = QProgressBar()
        self.progress_busy.setTextVisible(False)
        self.progress_busy.setRange(0, 0)
        layout.addWidget(self.progress_busy)
        layout.addStretch(1)
        return page

    def _build_downloads(self):
        downloads = QWidget()
        downloads.setObjectName("downloads")
        layout = QVBoxLayout(downloads)
        layout.setContentsMargins(0, 22, 0, 0)
        layout.setSpacing(4)
        header = QHBoxLayout()
        header.addWidget(caption(tr("загрузки"), on_field=True))
        header.addStretch(1)
        self.clear_button = QPushButton(tr("очистить"))
        self.clear_button.setProperty("kind", "fieldLink")
        self.clear_button.setCursor(Qt.PointingHandCursor)
        self.clear_button.clicked.connect(self._clear_finished)
        header.addWidget(self.clear_button)
        layout.addLayout(header)

        # Загрузки лежат прямо на поле: без карточек и линий, строки разделяет воздух.
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.viewport().setAutoFillBackground(False)
        self.scroll.setMinimumHeight(120)
        body = QWidget()
        body.setObjectName("scrollBody")
        self.rows_layout = QVBoxLayout(body)
        self.rows_layout.setContentsMargins(0, 0, 6, 0)
        self.rows_layout.setSpacing(2)
        self.rows_layout.addStretch(1)
        self.scroll.setWidget(body)
        layout.addWidget(self.scroll, 1)
        downloads.hide()
        return downloads

    # ----- настройки ---------------------------------------------------------

    def _apply_settings(self):
        if self.settings["mode"] not in ("video", "audio"):
            self.settings["mode"] = "video"
        self.mode_switch.set_value(self.settings["mode"])
        self.subs_check.blockSignals(True)
        self.subs_check.setChecked(bool(self.settings["subtitles"]))
        self.subs_check.blockSignals(False)
        self.folder_label.setText(self.settings["out_dir"])
        self._fill_quality()
        self._update_controls()

    def _save_settings(self):
        try:
            save_settings(self._settings_path, self.settings)
        except OSError as error:
            log.warning("settings not saved: %s", error)

    def _open_settings(self):
        dialog = SettingsDialog(self.settings, self.env, self, allow_update=not self._threads)
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        route_changed = (values["route_mode"], values["manual_proxy"]) != (
            self.settings["route_mode"], self.settings["manual_proxy"])
        self.settings.update(values)
        self._save_settings()
        if route_changed:
            self._check_environment()

    # ----- сеть и компоненты -------------------------------------------------

    def _check_environment(self):
        if self._probe is not None:
            return
        self.env = Environment(js_runtime=self.env.js_runtime, ffmpeg_dir=self.env.ffmpeg_dir)
        self._show_network_state()
        self._probe = EnvironmentProbe(self.settings["route_mode"], self.settings["manual_proxy"], self)
        self._probe.ready.connect(self._on_environment)
        self._run_thread(self._probe)

    def _on_environment(self, env):
        self._probe = None
        self.env = env
        self._show_network_state()
        missing = [name for name, available in (("FFmpeg", env.ffmpeg_dir), (tr("JS-движок"), env.js_runtime)) if not available]
        self.banner_text.setText(tr("Отсутствует: {components}.\nУстановка — в настройках.",
                                    components=tr(" и ").join(missing)) if missing else "")
        self.banner_text.setToolTip("\n".join(
            tr(hint) for available, hint in ((env.ffmpeg_dir, FFMPEG_HINT), (env.js_runtime, JS_HINT)) if not available
        ))
        self.banner.setVisible(bool(missing))
        self._start_pending_preview()

    def _show_network_state(self):
        env = self.env
        again = tr("По клику сеть проверяется заново.")
        if env.reachable is None:
            self.net_pill.show_state("warn", tr("проверка сети…"), tr("Поиск маршрута до YouTube"))
        elif env.reachable and env.proxy:
            proxy = redact_url_credentials(env.proxy)
            address = proxy.split("://")[-1]
            self.net_pill.show_state("done", tr("прокси {address}", address=address),
                                     tr("YouTube открывается через {proxy}.\n{again}", proxy=proxy, again=again))
        elif env.reachable:
            self.net_pill.show_state("done", tr("youtube напрямую"), tr("Без прокси.\n{again}", again=again))
        else:
            self.net_pill.show_state(
                "failed", tr("youtube недоступен"),
                tr("YouTube не ответил ни напрямую, ни через найденные прокси. Нужен включённый VPN.\n{again}",
                   again=again))

    # ----- ссылка и карточка -------------------------------------------------

    def _paste_from_clipboard(self):
        text = QGuiApplication.clipboard().text().strip()
        if text:
            self._last_clipboard = text
            self._show_url(text)
            self._fetch(normalize_url(text))

    def _maybe_paste_clipboard(self):
        """Ссылка скопирована, окно стало активным — ссылка уже вставлена."""
        text = QGuiApplication.clipboard().text().strip()
        if text == self._last_clipboard:
            return
        self._last_clipboard = text
        if is_youtube_url(text) and not self.url_edit.text().strip():
            self._show_url(text)
            self._fetch(normalize_url(text))

    def _show_url(self, text):
        # Вставленная ссылка видна с начала: по домену понятно, что это.
        self.url_edit.setText(text)
        self.url_edit.setCursorPosition(0)

    def _on_app_state(self, state):
        if state == Qt.ApplicationActive:
            self._maybe_paste_clipboard()

    def _on_url_enter(self):
        url = normalize_url(self.url_edit.text())
        if self.preview is not None and self.preview.url == url:
            self._start_download()
        elif url:
            self._fetch(url)

    def _on_url_edited(self, _text):
        self._fetch_serial += 1
        self._fetch_url = None
        self._pending_fetch = None
        self.preview = self.preview_thumb = None
        self._card_shown = False
        self._update_controls()
        self._update_stage()
        self._fetch_timer.start()

    def _fetch_from_field(self):
        url = normalize_url(self.url_edit.text())
        if not url or "." not in url or url == self._fetch_url:
            return
        self._fetch(url)

    def _fetch(self, url, as_playlist=False):
        if self._closing:
            return
        self._fetch_timer.stop()
        self._fetch_url = url
        self._fetch_as_playlist = as_playlist
        self._fetch_serial += 1
        self.preview = None
        self.preview_thumb = None
        self._show_card_loading()
        self._pending_fetch = (self._fetch_serial, url, as_playlist)
        self._start_pending_preview()

    def _start_pending_preview(self):
        if (self._closing or self._preview_worker is not None
                or self.env.reachable is None or self._pending_fetch is None):
            return
        serial, url, as_playlist = self._pending_fetch
        self._pending_fetch = None
        fetcher = InfoFetcher(
            serial, url, self.env,
            self.settings["cookies_browser"], self.settings["cookies_mode"], as_playlist, self,
        )
        fetcher.done.connect(self._on_preview)
        fetcher.failed.connect(self._on_preview_failed)
        fetcher.retrying.connect(self._on_preview_retrying)
        self._preview_worker = fetcher
        self._run_thread(fetcher)

    def _show_card_loading(self):
        self._card_shown = True
        self.card_thumb.resize_to(256, 144)
        self.card_thumb.set_image(None)
        self.card_figure.setText("")
        self.card_figure_unit.setText("")
        self.card_title.setText(self._fetch_url or "")
        self.card_meta.setText(tr("открывается ссылка…"))
        self.card_status.hide()
        self.card_busy.show()
        self.whole_playlist.hide()
        self.playlist_box.hide()
        self._update_controls()
        self._update_stage()

    def _on_preview(self, serial, preview, thumbnail):
        if serial != self._fetch_serial:
            return
        self.preview, self.preview_thumb = preview, thumbnail
        self.card_busy.hide()
        self.card_status.hide()
        is_playlist = preview.kind == "playlist"
        # У плейлиста главное — список, поэтому обложка меньше.
        self.card_thumb.resize_to(*((176, 99) if is_playlist else (256, 144)))
        self.card_thumb.set_image(thumbnail, theme.GLYPH["playlist" if is_playlist else "video"])
        self.card_title.setText(preview.title)
        if is_playlist:
            count = len(preview.entries)
            self.card_meta.setText(", ".join(part for part in (tr("плейлист"), preview.uploader) if part))
            more = "+" if count >= PLAYLIST_PREVIEW_LIMIT else ""
            # «+» в полный рост: маленький на базовой линии читается как опечатка, а не «больше».
            self.card_figure.setText(f"{count}{more}")
            self.card_figure_unit.setText(video_noun(count))
            self._fill_playlist(preview.entries)
        else:
            self.card_meta.setText(preview.uploader or "")
            self.card_figure.setText(format_duration(preview.duration) if preview.duration else "")
            self.card_figure_unit.setText("")
            self.playlist_box.hide()

        self.whole_playlist.blockSignals(True)
        self.whole_playlist.setChecked(self._fetch_as_playlist)
        self.whole_playlist.blockSignals(False)
        self.whole_playlist.setVisible(preview.in_playlist or self._fetch_as_playlist)

        self._fill_quality()
        self._update_controls()

    def _on_preview_failed(self, serial, message):
        if serial != self._fetch_serial:
            return
        self.card_busy.hide()
        self.card_thumb.set_image(None)
        self.card_meta.setText(tr("ссылка не открылась"))
        self.card_title.setText(self._fetch_url or "")
        self.card_figure.setText("")
        self.card_figure_unit.setText("")
        self.card_status.setText(message)
        set_role(self.card_status, "fieldError")
        self.card_status.show()
        self._update_controls()

    def _on_preview_retrying(self, serial, message):
        if serial != self._fetch_serial:
            return
        self.card_status.setText(tr(message))
        set_role(self.card_status, "fieldDim")
        self.card_status.show()

    def _on_whole_playlist_toggled(self, checked):
        if self._fetch_url:
            self._fetch(self._fetch_url, as_playlist=checked)

    def _fill_playlist(self, entries):
        self.playlist_list.blockSignals(True)
        self.playlist_list.clear()
        for number, title, duration in entries:
            item = QListWidgetItem(f"{number}.  {title}")
            item.setData(PlaylistDelegate.DURATION, format_duration(duration) if duration else "")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            item.setData(Qt.UserRole, number)
            self.playlist_list.addItem(item)
        self.playlist_list.blockSignals(False)
        self.playlist_box.show()
        self._on_selection_changed()

    def _checked_entries(self):
        items = (self.playlist_list.item(row) for row in range(self.playlist_list.count()))
        return [item.data(Qt.UserRole) for item in items if item.checkState() == Qt.Checked]

    def _check_all_entries(self, checked):
        self.playlist_list.blockSignals(True)
        for row in range(self.playlist_list.count()):
            self.playlist_list.item(row).setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.playlist_list.blockSignals(False)
        self._on_selection_changed()

    def _on_selection_changed(self):
        total = f"{self.playlist_list.count()}+" if self._playlist_truncated() else self.playlist_list.count()
        self.playlist_count.setText(tr("выбрано {selected} из {total}",
                                       selected=len(self._checked_entries()), total=total))
        self._update_controls()

    def _playlist_truncated(self):
        return self.preview is not None and len(self.preview.entries) >= PLAYLIST_PREVIEW_LIMIT

    # ----- параметры ---------------------------------------------------------

    def _fill_quality(self):
        if self.mode_switch.value() == "audio":
            choices = [(key, AUDIO_CHIPS[key], tr(text)) for key, (text, _codec, _bitrate) in AUDIO_CHOICES.items()]
            self.quality.set_choices(choices, self.settings["audio_format"], columns=3)
        else:
            if self.preview is not None and self.preview.kind == "video":
                tiers = list(self.preview.tiers)
                if self.trim_check.isChecked():
                    tiers = [tier for tier in tiers if tier <= FRAGMENT_MAX_HEIGHT]
                    best = tr("Лучшее для фрагмента, до {height}p", height=FRAGMENT_MAX_HEIGHT)
                else:
                    best = tr("Лучшее доступное, {height}p", height=tiers[0]) if tiers else tr("Лучшее доступное")
            else:
                tiers = list(QUALITY_TIERS)
                best = tr("Лучшее доступное")
            choices = [(None, tr("лучшее"), best)] + [(tier, f"{tier}p", tier_name(tier)) for tier in tiers]
            preferred = self.settings["video_height"]
            value = None
            if preferred is not None and tiers:
                # Нет нужного качества — берётся ближайшее ниже, а не «лучшее».
                lower = [tier for tier in tiers if tier <= preferred]
                value = lower[0] if lower else tiers[-1]
            self.quality.set_choices(choices, value, columns=4)
        self._update_controls()

    def _on_mode_changed(self, mode):
        self.settings["mode"] = mode
        self._fill_quality()

    def _on_quality_changed(self, value):
        if self.mode_switch.value() == "audio":
            self.settings["audio_format"] = value
        else:
            self.settings["video_height"] = value
        self._update_controls()

    def _on_subtitles_toggled(self, checked):
        self.settings["subtitles"] = checked
        self._update_controls()

    def _on_trim_toggled(self, checked):
        self.trim_fields.setVisible(checked)
        self._show_trim_error("")
        if checked:
            self.trim_start.setFocus()
        self._fill_quality()

    def _on_trim_edited(self, _text):
        self._show_trim_error("")
        self._update_controls()

    def _show_trim_error(self, message):
        self.trim_error.setText(message)
        self.trim_error.setVisible(bool(message))
        for edit in (self.trim_start, self.trim_end):
            edit.setProperty("invalid", bool(message))
            theme.repolish(edit)

    def _choose_folder(self):
        options = QFileDialog.Option.ShowDirsOnly
        system_language = next(iter(QLocale.system().uiLanguages()), "").split("-")[0].lower()
        if language() != system_language:
            options |= QFileDialog.Option.DontUseNativeDialog
        folder = QFileDialog.getExistingDirectory(self, tr("Папка для сохранения"), self.settings["out_dir"],
                                                  options=options)
        if folder:
            self.settings["out_dir"] = os.path.normpath(folder)
            self.folder_label.setText(self.settings["out_dir"])
            self._save_settings()

    def _open_folder(self):
        folder = self.settings["out_dir"]
        try:
            os.makedirs(folder, exist_ok=True)
            os.startfile(folder)
        except OSError as error:
            QMessageBox.warning(self, APP_TITLE, tr("Не получилось открыть папку:\n{error}", error=error))

    def _update_controls(self):
        preview = self.preview
        is_video_mode = self.mode_switch.value() == "video"
        is_playlist = preview is not None and preview.kind == "playlist"

        has_subs = preview is None or is_playlist or preview.has_subtitles
        self.subs_check.setEnabled(is_video_mode and has_subs)
        self.subs_check.setToolTip("" if has_subs else tr("У этого видео нет субтитров"))
        self.trim_check.setEnabled(not is_playlist)
        self.trim_check.setToolTip(tr("Для плейлиста фрагмент не выбирается") if is_playlist else "")
        self.trim_fields.setVisible(self.trim_check.isChecked() and not is_playlist)

        text, enabled = self._download_label()
        self.download_button.setText(text)
        self.download_button.setEnabled(enabled)

    def _download_label(self):
        preview = self.preview
        if preview is None:
            return tr("скачать"), False
        audio_key = self.quality.value() if self.mode_switch.value() == "audio" else None
        codec = AUDIO_CHOICES[audio_key][1] if audio_key in AUDIO_CHOICES else None
        if preview.kind == "playlist":
            count = len(self._checked_entries())
            if count == 0:
                return tr("ничего не выбрано"), False
            # Отмечено всё в урезанном списке — скачается весь плейлист, а не только показанное.
            whole = count == self.playlist_list.count() and self._playlist_truncated()
            what = tr("весь плейлист") if whole else video_count(count)
            return (tr("скачать {what} в {codec}", what=what, codec=codec) if codec
                    else tr("скачать {what}", what=what)), True
        if self.trim_check.isChecked():
            return tr("скачать фрагмент"), True
        if codec:
            return tr("скачать {what}", what=codec), True
        height = self.quality.value()
        return (tr("скачать {what}", what=f"{height}p") if height else tr("скачать")), True

    # ----- скачивание --------------------------------------------------------

    def _start_download(self):
        preview = self.preview
        if preview is None or not self.download_button.isEnabled():
            return
        out_dir = self.settings["out_dir"]
        try:
            os.makedirs(out_dir, exist_ok=True)
        except OSError as error:
            QMessageBox.warning(self, APP_TITLE, tr("Не получилось создать папку {folder}:\n{error}",
                                                    folder=out_dir, error=error))
            return

        mode = self.mode_switch.value()
        is_playlist = preview.kind == "playlist"
        trim = None
        if not is_playlist and self.trim_check.isChecked():
            try:
                trim = parse_range(
                    self.trim_start.text(), self.trim_end.text(),
                    duration=preview.duration, required=True,
                )
            except ValueError as error:
                self._show_trim_error(str(error).capitalize())
                return

        playlist_items = None
        if is_playlist:
            checked = self._checked_entries()
            # Всё отмечено — скачивается плейлист целиком, даже если в карточке показана только часть.
            if len(checked) < self.playlist_list.count():
                playlist_items = tuple(checked)

        if mode == "audio":
            _text, codec, bitrate = AUDIO_CHOICES[self.quality.value()]
            height = None
        else:
            codec, bitrate = "mp3", None
            height = self.quality.value()
        subtitles = mode == "video" and self.subs_check.isEnabled() and self.subs_check.isChecked()

        request = DownloadRequest(
            url=preview.url, out_dir=out_dir, mode=mode, max_height=height,
            audio_codec=codec, audio_bitrate=bitrate, subtitles=subtitles, trim=trim,
            is_playlist=is_playlist, playlist_items=playlist_items,
        )
        job = Job(title=preview.title, request=request, thumbnail=self.preview_thumb,
                  kind=mode, detail=self._describe_choice(request))
        self._save_settings()

        self.queue.add(job)
        self._add_row(job, newest=True)
        self._reset_input()
        self._update_title()
        self.scroll.verticalScrollBar().setValue(0)

    def _describe_choice(self, request):
        parts = []
        if request.is_playlist:
            if request.playlist_items:
                parts.append(tr("плейлист, {videos}", videos=video_count(len(request.playlist_items))))
            elif self._playlist_truncated():
                parts.append(tr("плейлист целиком"))
            else:
                parts.append(tr("плейлист, {videos}", videos=video_count(len(self.preview.entries))))
        if request.mode == "audio":
            parts.append(tr(AUDIO_CHOICES[self.quality.value()][0]))
        else:
            parts.append(f"{request.max_height}p" if request.max_height else tr("лучшее качество"))
            if request.subtitles:
                parts.append(tr("субтитры"))
        if request.trim:
            start, end = request.trim
            parts.append(tr("фрагмент {start}–{end}", start=format_duration(start),
                            end=format_duration(end) if end is not None else tr("конец")))
        return ", ".join(parts)

    def _reset_input(self):
        self._fetch_serial += 1  # ответ ещё летящего запроса больше не нужен
        self._fetch_url = None
        self._fetch_as_playlist = False
        self._pending_fetch = None
        self._fetch_timer.stop()
        self.preview = None
        self.preview_thumb = None
        self._card_shown = False
        self.url_edit.clear()
        self.trim_check.setChecked(False)
        self.trim_start.clear()
        self.trim_end.clear()
        self._fill_quality()
        self._update_stage()

    def _start_worker(self, job):
        worker = DownloadWorker(job, self.env, self.settings["cookies_browser"], self.settings["cookies_mode"], self)
        worker.progressed.connect(self._on_job_progress)
        worker.completed.connect(self._on_job_completed)
        self._run_thread(worker)
        return worker

    def _on_job_progress(self, job_id, progress):
        job = self.queue.get(job_id)
        if job.state != RUNNING:
            return
        job.progress = progress
        row = self._rows.get(job)
        if row is not None:
            row.refresh()
        self._update_title()

    def _on_job_completed(self, job_id, ok, message, path):
        self.queue.finish(job_id, ok, message or None, path or None)
        job = self.queue.get(job_id)
        if job.state == DONE:
            self._remember(job)
        self._refresh_rows()
        self._update_title()
        if self.queue.running is None and not self.isActiveWindow():
            QApplication.alert(self)

    def _cancel_job(self, job):
        self.queue.cancel(job.id)
        if job.state == RUNNING:
            fraction = job.progress.fraction if job.progress else None
            job.progress = Progress(fraction=fraction, stage=tr("Остановка…"))
        self._refresh_rows()
        self._update_title()

    def _retry_job(self, job):
        self.queue.retry(job.id)
        self._refresh_rows()
        self._update_title()

    # ----- список загрузок и история ----------------------------------------

    def _add_row(self, job, newest):
        row = JobRow(job)
        row.cancel_requested.connect(self._cancel_job)
        row.retry_requested.connect(self._retry_job)
        row.reveal_requested.connect(lambda finished: reveal_in_explorer(finished.path))
        self._rows[job] = row
        # Внизу всегда остаётся растяжка.
        position = 0 if newest else self.rows_layout.count() - 1
        self.rows_layout.insertWidget(position, row)
        self.downloads.show()

    def _refresh_rows(self):
        for row in self._rows.values():
            row.refresh()
        self.downloads.setVisible(bool(self._rows))

    def _remember(self, job):
        thumbnail_file = ""
        if job.thumbnail:
            try:
                self._thumbs_dir.mkdir(parents=True, exist_ok=True)
                target = self._thumbs_dir / f"{int(time.time() * 1000)}.img"
                target.write_bytes(job.thumbnail)
                thumbnail_file = str(target)
            except OSError:
                pass
        try:
            append_history(self._history_path, {
                "title": job.title, "path": job.path, "kind": job.kind, "detail": job.detail,
                "message": job.message or "", "thumbnail": thumbnail_file, "finished_at": time.time(),
            })
        except OSError as error:
            log.warning("history not saved: %s", error)

    def _load_history(self):
        entries = load_history(self._history_path)
        for entry in entries[:HISTORY_ROWS]:
            thumbnail = None
            thumbnail_file = entry.get("thumbnail")
            if thumbnail_file:
                try:
                    path = Path(thumbnail_file).resolve()
                    if path.parent == self._thumbs_dir.resolve():
                        with path.open("rb") as file:
                            thumbnail = file.read(THUMBNAIL_LIMIT + 1)
                            if len(thumbnail) > THUMBNAIL_LIMIT:
                                thumbnail = None
                except (OSError, ValueError):
                    pass
            job = Job(
                title=entry.get("title") or tr("Без названия"), request=None, state=DONE,
                path=entry.get("path"), message=entry.get("message") or None,
                thumbnail=thumbnail, kind=entry.get("kind", "video"), detail=entry.get("detail", ""),
            )
            self._add_row(job, newest=False)
        self._prune_thumbnails({entry.get("thumbnail") for entry in entries})

    def _prune_thumbnails(self, keep):
        if not self._thumbs_dir.is_dir():
            return
        for file in self._thumbs_dir.iterdir():
            if str(file) not in keep:
                try:
                    file.unlink()
                except OSError:
                    pass

    def _clear_finished(self):
        for job, row in list(self._rows.items()):
            if job.state in (DONE, FAILED, CANCELLED):
                self.rows_layout.removeWidget(row)
                row.deleteLater()
                del self._rows[job]
        self.queue.forget_finished()
        try:
            clear_history(self._history_path)
        except OSError as error:
            log.warning("history not cleared: %s", error)
        self._prune_thumbnails(set())
        self._refresh_rows()

    def _update_title(self):
        job = self.queue.running
        progress = job.progress if job is not None else None
        if progress is not None and progress.fraction is not None:
            self.setWindowTitle(f"{APP_TITLE} {progress.fraction * 100:.0f}%")
        elif job is not None:
            self.setWindowTitle(tr("{title}, скачивание", title=APP_TITLE))
        else:
            self.setWindowTitle(APP_TITLE)
        self._update_stage()

    def _update_stage(self):
        """Что на поле: ссылка, если она открыта; иначе идущая загрузка; иначе «Hi.»."""
        job = self.queue.running
        progress = job.progress if job is not None else None
        fraction = progress.fraction if progress is not None else None
        if job is not None:
            known = fraction is not None
            self.progress_figure.setVisible(known)
            self.progress_busy.setVisible(not known)
            self.progress_figure.setText(theme.figure_html(f"{fraction * 100:.0f}", "%", 150) if known else "")
            self.progress_title.setText(job.title)
            waiting = sum(1 for queued in self.queue.jobs if queued.state == QUEUED)
            detail = describe_detail(progress)
            self.progress_detail.setText(tr("{detail}, ещё {count} в очереди", detail=detail, count=waiting)
                                         if waiting else detail)
        if self._card_shown:
            page = self.card_page
        elif job is not None:
            page = self.progress_page
        else:
            page = self.idle_page
        self.stage.setCurrentWidget(page)
        # Пока загрузка крупно на поле, её строка не повторяет цифры.
        for row in self._rows.values():
            row.set_on_stage(page is self.progress_page and row.job is job)

    # ----- потоки и события окна ---------------------------------------------

    def _run_thread(self, thread):
        self._threads.add(thread)
        thread.finished.connect(self._on_thread_finished)
        thread.start()

    def _on_thread_finished(self):
        thread = self.sender()
        self._threads.discard(thread)
        if thread is self._preview_worker:
            self._preview_worker = None
            self._start_pending_preview()
        thread.deleteLater()
        if self._closing and not self._threads:
            QTimer.singleShot(0, self.close)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._shown_once:
            self._shown_once = True
            theme.apply_title_bar(self)
            QTimer.singleShot(250, self._maybe_paste_clipboard)

    def closeEvent(self, event):
        if self._closing:
            if self._threads:
                event.ignore()
            else:
                event.accept()
            return
        active = [job for job in self.queue.jobs if job.state in (RUNNING, QUEUED)]
        if active and not ask(self, tr("Идёт скачивание"), tr("Закрыть приложение и остановить скачивание?")):
            event.ignore()
            return
        self._closing = True
        self._fetch_timer.stop()
        self._pending_fetch = None
        self._fetch_serial += 1
        for job in active:
            self._cancel_job(job)
        self._save_settings()
        if self._threads:
            self.setEnabled(False)
            self.setWindowTitle(tr("{title}, завершение…", title=APP_TITLE))
            event.ignore()
        else:
            event.accept()

    def paintEvent(self, event):
        # Панель — ровная светлая заливка с едва заметным зерном; поле рисует себя само.
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(theme.C["panel"]))
        theme.paint_grain(painter, self.rect(), 0.035)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        mime = event.mimeData()
        text = mime.urls()[0].toString() if mime.hasUrls() else mime.text()
        if text.strip():
            self._show_url(text.strip())
            self._fetch(normalize_url(text))
