import struct

from app.icon import ICON_SIZES, write_ico


def test_writes_multi_size_ico_without_a_running_app(tmp_path):
    # build_portable.ps1 рисует значок для helloytd.exe ещё до первого запуска окна.
    path = tmp_path / "icon.ico"
    write_ico(path)
    data = path.read_bytes()
    reserved, kind, count = struct.unpack_from("<HHH", data)
    assert (reserved, kind, count) == (0, 1, len(ICON_SIZES))
    first_offset = struct.unpack_from("<I", data, 6 + 12)[0]
    assert data[first_offset:first_offset + 8] == b"\x89PNG\r\n\x1a\n"


def test_artwork_is_an_ios_shaped_squircle():
    from PySide6.QtGui import QImage

    from app.icon import ARTWORK

    image = QImage(str(ARTWORK))
    size = image.width()
    assert image.height() == size
    alpha = lambda x, y: image.pixelColor(int(x), int(y)).alpha()  # noqa: E731
    assert alpha(size * 0.02, size * 0.02) == 0          # углы прозрачные
    assert alpha(size / 2, size / 2) == 255              # середина залита
    assert alpha(size * 0.05, size / 2) == 255           # стороны почти прямые — это не круг
    assert alpha(size * 0.12, size * 0.12) == 255        # и угол полный, не как у круга
