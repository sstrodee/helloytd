"""60 секунд повторных действий с реальным окном Qt и временными данными."""

import ctypes
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QPushButton

from app import theme
from app.window import MainWindow


class MemoryCounters(ctypes.Structure):
    _fields_ = [("size", ctypes.c_ulong), ("faults", ctypes.c_ulong)] + [
        (name, ctypes.c_size_t) for name in (
            "peak_working_set", "working_set", "peak_paged", "paged",
            "peak_non_paged", "non_paged", "pagefile", "peak_pagefile",
        )
    ]


def working_set():
    current_process = ctypes.windll.kernel32.GetCurrentProcess
    current_process.restype = ctypes.c_void_p
    memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
    memory_info.argtypes = (ctypes.c_void_p, ctypes.POINTER(MemoryCounters), ctypes.c_ulong)
    counters = MemoryCounters()
    counters.size = ctypes.sizeof(counters)
    if not memory_info(current_process(), ctypes.byref(counters), counters.size):
        raise ctypes.WinError()
    return round(counters.working_set / 1024 ** 2, 2)


class TestWindow(MainWindow):
    def _check_environment(self):
        pass

    def showEvent(self, event):
        self._shown_once = True
        super().showEvent(event)


def main():
    app = QApplication([])
    theme.apply(app)
    with tempfile.TemporaryDirectory(prefix="audit-ui-", dir=ROOT / ".test-deps") as folder:
        window = TestWindow(Path(folder))
        window.resize(960, 640)
        window.show()
        app.processEvents()
        samples, rss = [], []
        cpu, start = time.process_time(), time.perf_counter()
        while time.perf_counter() - start < 60:
            tick = time.perf_counter()
            mode = "video" if len(samples) % 2 == 0 else "audio"
            window.mode_switch.set_value(mode)
            window._on_mode_changed(mode)
            window.trim_check.setChecked(mode == "video")
            app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            buttons = window.quality.buttons()
            assert len(window.quality.findChildren(QPushButton)) == len(buttons)
            assert all(window.quality.rect().contains(button.geometry()) for button in buttons)
            samples.append(time.perf_counter() - tick)
            if len(rss) <= (time.perf_counter() - start) / 10:
                rss.append(working_set())
            time.sleep(0.005)
        elapsed = time.perf_counter() - start
        window.close()
        samples.sort()
        print(json.dumps({
            "seconds": elapsed, "iterations": len(samples), "errors": 0,
            "process_cpu_seconds": time.process_time() - cpu, "working_set_mib": rss,
            **{f"p{p}_ms": round(samples[(len(samples) * p - 1) // 100] * 1000, 3) for p in (50, 95, 99)},
        }))


if __name__ == "__main__":
    main()
