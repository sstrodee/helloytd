"""Smoke test launcher. Run as helloytd.exe <absolute path to this script>."""

import logging
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app import main as entry


class SmokeWindow(entry.MainWindow):
    def _check_environment(self):
        pass

    def _maybe_paste_clipboard(self):
        pass

    def showEvent(self, event):
        self._shown_once = True  # Не читать реальный буфер обмена в тесте.
        super().showEvent(event)
        QTimer.singleShot(50, self.finish_smoke)

    def finish_smoke(self):
        QApplication.instance().exit(0 if self.isVisible() and self.width() >= 960 else 2)


app_dir = Path(sys.executable).resolve().parent
assert Path(entry.__file__).resolve().is_relative_to(app_dir / "app")
entry.MainWindow = SmokeWindow
entry.install_crash_dialog = lambda _folder: None  # Ошибки событий должны попасть в stderr теста.
with tempfile.TemporaryDirectory(prefix="helloytd-launch-", dir=Path.cwd()) as folder:
    status = entry.main(folder)
    assert Path(folder, "app.log").is_file()
    assert not Path(folder, "instance.lock").exists()
    logging.shutdown()
sys.exit(status)
