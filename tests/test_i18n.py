from string import Formatter

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.formats import format_bytes, format_speed, parse_range
from app.i18n import language, resolve_language, set_language, tr
from app.options import ERROR_MESSAGES, friendly_error, summarize_result
from app.preview import Preview
from app.progress import DOWNLOADING, Progress, STAGE_LABELS, describe_detail
from app.settings_dialog import SettingsDialog
from app.storage import load_settings, save_settings
from app.translations_en import ENGLISH
from app.widgets import JobRow
from app.window import MainWindow
from app.workers import COOKIE_RETRY_STAGE, Environment


@pytest.fixture
def english():
    previous = language()
    set_language("en")
    yield
    set_language(previous)


@pytest.mark.parametrize(
    "preference, system, expected",
    [
        ("auto", ["ru-Cyrl-RU", "en-US"], "ru"),
        ("auto", ["en-GB", "ru-RU"], "en"),
        ("auto", ["de-DE"], "en"),
        ("auto", [], "en"),
        ("ru", ["en-US"], "ru"),
        ("en", ["ru-RU"], "en"),
    ],
)
def test_locale_selection(preference, system, expected):
    assert resolve_language(preference, system) == expected


def test_english_catalog_keeps_interpolation_fields():
    formatter = Formatter()
    for russian, english in ENGLISH.items():
        fields = lambda text: {name for _, name, _, _ in formatter.parse(text) if name is not None}
        assert fields(russian) == fields(english), russian


def test_all_state_and_error_strings_have_english_translations(english):
    for phrase in (*ERROR_MESSAGES.values(), *STAGE_LABELS.values(), *JobRow.STATES.values(), COOKIE_RETRY_STAGE):
        assert tr(phrase) != phrase


def test_english_formats_errors_and_playlist_status(english):
    assert format_bytes(1536) == "1.5 KB"
    assert format_speed(1024 * 1024) == "1.0 MB/s"
    assert describe_detail(Progress(stage=DOWNLOADING, eta=64, item=2, item_count=5)) == (
        "Video 2 of 5, 1 min 4 s left"
    )
    assert friendly_error("HTTP Error 429") == "YouTube has temporarily rate-limited requests. Try again in a few minutes."
    assert summarize_result({"entries": [None]}, True)[1] == "None of the playlist videos could be downloaded."
    with pytest.raises(ValueError, match="The clip end must be after the start"):
        parse_range("1:20", "1:10", required=True)


def test_english_window_settings_and_playlist_actions(english, tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, "_check_environment", lambda self: None)
    window = MainWindow(tmp_path)
    assert window.url_edit.placeholderText() == "video or playlist"
    assert window.trim_check.text() == "clip only"
    assert window.download_button.text() == "download"

    dialog = SettingsDialog(window.settings, Environment(), window)
    assert dialog.windowTitle() == "Settings"
    assert [dialog.language_combo.itemText(i) for i in range(dialog.language_combo.count())] == [
        "system default", "English", "Русский",
    ]
    dialog.language_combo.setCurrentIndex(dialog.language_combo.findData("ru"))
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, dialog.values())
    assert load_settings(settings_path)["language"] == "ru"

    entries = ((1, "First", 35), (2, "Second", 48))
    window._on_preview(0, Preview("url", "playlist", "Playlist", "Creator", None, None, entries=entries), None)
    assert window.download_button.text() == "download 2 videos"
    window.playlist_list.item(1).setCheckState(Qt.CheckState.Unchecked)
    assert window.download_button.text() == "download 1 video"
    window.deleteLater()
    app.processEvents()
