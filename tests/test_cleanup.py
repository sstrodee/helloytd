import threading

from app.cleanup import remove_partial_files


def test_removes_every_download_leftover(tmp_path):
    base = tmp_path / "Video.f628.mp4"
    for name in ("Video.f628.mp4", "Video.f628.mp4.part", "Video.f628.mp4.ytdl", "Video.f628.mp4.part-Frag7.part"):
        (tmp_path / name).write_bytes(b"x")
    (tmp_path / "Other.mp4").write_bytes(b"x")
    remove_partial_files([str(base)])
    assert [path.name for path in tmp_path.iterdir()] == ["Other.mp4"]


def test_waits_for_a_file_that_is_still_being_released(tmp_path):
    # Только что отменённая загрузка ещё держит .part открытым (WinError 32).
    part = tmp_path / "Video.mp4.part"
    handle = open(part, "wb")
    threading.Timer(0.3, handle.close).start()
    remove_partial_files([str(tmp_path / "Video.mp4")], attempts=20, delay=0.1)
    assert not part.exists()


def test_missing_files_are_fine(tmp_path):
    remove_partial_files([str(tmp_path / "never-existed.mp4")], attempts=1, delay=0)
