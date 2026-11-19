"""Точка входа: pythonw -m app.main — так его запускает ярлык."""

import ctypes
import logging
import os
import sys
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QMessageBox

from . import theme
from .icon import app_icon
from .storage import app_data_dir, keep_caches_inside, lock_data_dir
from .window import APP_TITLE, MainWindow

APP_ID = "helloytd"
ROOT = Path(__file__).resolve().parent.parent


def setup_logging(folder):
    folder.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(folder / "app.log", maxBytes=1_000_000, backupCount=1, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)


def install_crash_dialog(folder):
    """Под pythonw нет консоли: без этого необработанная ошибка молча закрыла бы окно."""

    def handle(kind, value, tb):
        details = "".join(traceback.format_exception(kind, value, tb))
        logging.getLogger("ytdl").error("необработанная ошибка:\n%s", details)
        if QApplication.instance() is not None:
            QMessageBox.critical(
                None, APP_TITLE,
                f"Что-то пошло не так:\n\n{value}\n\nПодробности в журнале:\n{folder / 'app.log'}",
            )

    sys.excepthook = handle


def main(folder=None):
    folder = Path(folder) if folder else app_data_dir(ROOT)
    keep_caches_inside(folder, os.environ)
    # У pythonw нет stdout/stderr; библиотека, решившая что-то напечатать, упала бы.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    if sys.platform == "win32" and Path(sys.executable).stem.lower().startswith("python"):
        # Запуск через python(w).exe: своя группа на панели задач вместо значка Python.
        # У helloytd.exe Windows свяжет окно с закреплённым значком сама.
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)

    theme.prefer_grey_text(os.environ)
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    lock = lock_data_dir(folder)
    if lock is None:
        QMessageBox.information(None, APP_TITLE, "Приложение уже запущено для этой папки данных.")
        return 0
    setup_logging(folder)
    install_crash_dialog(folder)
    app.setWindowIcon(app_icon())
    theme.apply(app)
    window = MainWindow(folder)
    window.show()
    try:
        return app.exec()
    finally:
        lock.unlock()


if __name__ == "__main__":
    sys.exit(main())
