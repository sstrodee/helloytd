"""Локальная проверка yt-dlp и FFmpeg. Все файлы и сетевой трафик тестовые."""

import functools
import hashlib
import http.server
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.environment import find_ffmpeg_dir
from app.jobs import Job
from app.options import DownloadRequest, summarize_result
from app.workers import DownloadWorker, Environment


class Handler(http.server.SimpleHTTPRequestHandler):
    failures = 0
    retry_requests = 0

    def log_message(self, *_args):
        pass

    def do_GET(self):
        # Generic extractor открывает URL, затем downloader открывает медиа.
        if self.path == "/retry.mp4":
            Handler.retry_requests += 1
            if Handler.retry_requests == 2:
                Handler.failures += 1
                self.send_error(503)
                return
        super().do_GET()

    def send_head(self):
        match = re.fullmatch(r"bytes=(\d+)-", self.headers.get("Range", ""))
        path = Path(self.translate_path(self.path))
        if not match or not path.is_file():
            return super().send_head()
        start, size = int(match[1]), path.stat().st_size
        if start >= size:
            self.send_error(416)
            return None
        handle = path.open("rb")
        handle.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(str(path)))
        self.send_header("Content-Length", str(size - start))
        self.send_header("Content-Range", f"bytes {start}-{size - 1}/{size}")
        self.end_headers()
        return handle

    def copyfile(self, source, outputfile):
        try:
            if self.path == "/slow.mp4":
                while chunk := source.read(8192):
                    outputfile.write(chunk)
                    time.sleep(0.02)
            else:
                shutil.copyfileobj(source, outputfile)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # FFmpeg закрывает старый запрос при seek.


def run_case(base, output, ffdir, name, *, trim=None):
    request = DownloadRequest(base + "/" + name, str(output), max_height=360, trim=trim)
    worker = DownloadWorker(Job(name, request, id=1), Environment(ffmpeg_dir=ffdir), None, "never")
    start = time.monotonic()
    result = worker._download(None)
    ok, message, path = summarize_result(result, False, path_ready=worker._file_ready)
    assert ok, message
    data = subprocess.check_output([
        str(Path(ffdir) / "ffprobe.exe"), "-v", "error", "-show_entries", "format=duration",
        "-of", "json", path,
    ])
    duration = float(json.loads(data)["format"]["duration"])
    expected = trim[1] - trim[0] if trim else 6
    assert abs(duration - expected) <= 0.08, (name, expected, duration)
    print(json.dumps({"media": name, "duration": duration, "elapsed": round(time.monotonic() - start, 3)}))
    return Path(path)


def check_cancel(base, output, ffdir):
    request = DownloadRequest(base + "/slow.mp4", str(output), max_height=360)
    worker = DownloadWorker(Job("slow", request, id=1), Environment(ffmpeg_dir=ffdir), None, "never")
    completed = []
    worker.progressed.connect(lambda _job, _progress: worker.cancel())
    worker.completed.connect(lambda *result: completed.append(result))
    start = time.monotonic()
    worker.run()
    assert completed == [(1, False, "", "")]
    assert not list(output.glob("*slow*"))
    print(json.dumps({"media": "cancel mid-transfer", "elapsed": round(time.monotonic() - start, 3)}))


def main():
    ffdir = find_ffmpeg_dir()
    if not ffdir:
        raise RuntimeError("FFmpeg требуется для интеграционного прогона")
    ffmpeg = str(Path(ffdir) / "ffmpeg.exe")
    with tempfile.TemporaryDirectory(prefix="audit-media-", dir=ROOT / ".test-deps") as tmp:
        folder = Path(tmp)
        subprocess.run([
            ffmpeg, "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=25",
            "-f", "lavfi", "-i", "sine=frequency=440", "-t", "6", "-c:v", "libx264",
            "-g", "25", "-c:a", "aac", "-movflags", "+faststart", "clip.mp4",
        ], cwd=folder, check=True, timeout=20)
        subprocess.run([
            ffmpeg, "-v", "error", "-i", "clip.mp4", "-c", "copy", "-hls_time", "1",
            "-hls_list_size", "0", "clip.m3u8",
        ], cwd=folder, check=True, timeout=20)
        (folder / "retry.mp4").write_bytes((folder / "clip.mp4").read_bytes())
        (folder / "slow.mp4").write_bytes((folder / "clip.mp4").read_bytes())
        handler = functools.partial(Handler, directory=tmp)
        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                url = f"http://127.0.0.1:{server.server_port}"
                output = folder / "output"
                first = run_case(url, output, ffdir, "clip.mp4")
                digest = hashlib.sha256(first.read_bytes()).digest()
                run_case(url, output, ffdir, "clip.mp4")
                assert hashlib.sha256(first.read_bytes()).digest() == digest
                run_case(url, output, ffdir, "clip.mp4", trim=(2, 4))
                run_case(url, output, ffdir, "clip.m3u8", trim=(2, 4))
                run_case(url, output, ffdir, "retry.mp4")
                assert Handler.failures == 1 and Handler.retry_requests >= 3
                check_cancel(url, output, ffdir)
            finally:
                server.shutdown()
                thread.join()


if __name__ == "__main__":
    main()
