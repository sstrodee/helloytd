import json

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QCloseEvent, QKeyEvent
from PySide6.QtWidgets import QApplication
from yt_dlp.utils import DownloadCancelled

from app.formats import parse_timecode, trim_label
from app.jobs import Job, JobQueue
from app.links import is_youtube_url, redact_url_credentials
from app.options import DownloadRequest, build_ydl_options, info_ydl_options, summarize_result
from app.preview import Preview
from app.storage import DEFAULT_SETTINGS, load_settings, lock_data_dir, save_settings
from app.window import MainWindow
from app.workers import DownloadWorker, Environment


@pytest.mark.parametrize("text", ["NaN", "inf", "1e900", "9" * 400 + ":00"])
def test_invalid_timecodes_have_a_validation_error(text):
    with pytest.raises(ValueError):
        parse_timecode(text)


def test_distinct_subsecond_ranges_have_distinct_output_names():
    assert trim_label(1.125, 2.25) != trim_label(1.5, 2.75)


def test_malformed_clipboard_link_is_ignored():
    assert not is_youtube_url("https://[")


def test_diagnostic_proxy_url_has_no_credentials():
    assert redact_url_credentials("proxy=http://user:dummy@127.0.0.1:8080") == "proxy=http://127.0.0.1:8080"


def test_corrupt_field_types_restore_only_affected_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({
        "mode": "audio", "audio_format": [],
        "out_dir": 123, "manual_proxy": {}, "subtitles": "false", "video_height": True,
    }), encoding="utf-8")
    assert load_settings(path) == dict(DEFAULT_SETTINGS, mode="audio")


def test_direct_route_is_explicit_in_preview_and_download():
    request = DownloadRequest("https://youtu.be/test", ".")
    assert info_ydl_options(False, proxy=None)["proxy"] == build_ydl_options(request, proxy=None)["proxy"] == ""


def test_cancel_records_partial_before_raising(tmp_path):
    worker = DownloadWorker(Job("test", DownloadRequest("https://youtu.be/test", str(tmp_path))),
                            Environment(), None, "never")
    part = str(tmp_path / "download.mp4.part")
    worker.cancel()
    with pytest.raises(DownloadCancelled):
        worker._on_download({"status": "downloading", "tmpfilename": part})
    assert part in worker._partial_files


def test_history_lock_excludes_a_second_app_and_recovers_after_release(tmp_path):
    first = lock_data_dir(tmp_path)
    assert first is not None
    assert lock_data_dir(tmp_path) is None
    first.unlock()
    assert lock_data_dir(tmp_path) is not None


def test_failed_atomic_replace_preserves_current_settings(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    save_settings(path, DEFAULT_SETTINGS)
    def denied(*_args):
        raise PermissionError("fixture")
    monkeypatch.setattr(type(path), "replace", denied)
    with pytest.raises(PermissionError):
        save_settings(path, dict(DEFAULT_SETTINGS, mode="audio"))
    assert load_settings(path) == DEFAULT_SETTINGS
    assert list(tmp_path.iterdir()) == [path]


def test_missing_or_empty_file_is_not_a_completed_download(tmp_path):
    target = tmp_path / "clip.mp4"
    info = {"requested_downloads": [{"filepath": str(target)}]}
    for data in (None, b"", b"fixture"):
        if data is not None:
            target.write_bytes(data)
        ok, _, _ = summarize_result(info, False, path_ready=DownloadWorker._file_ready)
        assert ok == bool(data)


@pytest.fixture
def window(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, "_check_environment", lambda self: None)
    result = MainWindow(tmp_path)
    result.settings["out_dir"] = str(tmp_path / "output")
    yield result
    result.deleteLater()
    app.processEvents()


def test_editing_link_invalidates_preview_before_debounce(window):
    url = "https://youtu.be/old"
    window._show_url(url)
    window._fetch_url = url
    window.preview = Preview(url, "video", "old", "", 20, None)
    window.queue = JobQueue(lambda _job: object())
    window._update_controls()
    assert window.download_button.isEnabled()
    window.url_edit.selectAll()
    QApplication.sendEvent(window.url_edit, QKeyEvent(QEvent.KeyPress, Qt.Key_Backspace, Qt.NoModifier))
    window.download_button.click()
    assert not window.download_button.isEnabled()
    assert not window.queue.jobs


def test_latest_link_replaces_pending_preview_while_loader_is_busy(window, monkeypatch):
    started = []
    monkeypatch.setattr(window, "_run_thread", lambda thread: started.append(thread.url))
    window.env = Environment(reachable=True)
    for name in ("first", "second", "last"):
        window._fetch(f"https://youtu.be/{name}")
    assert started == ["https://youtu.be/first"]
    window._preview_worker = None
    window._start_pending_preview()
    assert started == ["https://youtu.be/first", "https://youtu.be/last"]


def test_close_waits_for_finished_signal_without_blocking_ui(window):
    thread = object()
    window._threads.add(thread)
    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted()
    assert window._closing and not window.isEnabled()
    window._threads.remove(thread)
    window.closeEvent(event)
    assert event.isAccepted()
