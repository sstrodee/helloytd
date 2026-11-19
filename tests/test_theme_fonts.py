from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QComboBox, QListWidget

from app import theme

app = QApplication.instance() or QApplication([])


def test_bundled_fonts_are_registered():
    families = theme.load_fonts()
    assert theme.SERIF in families
    assert theme.SANS in families


def test_loading_twice_does_not_register_duplicates():
    assert theme.load_fonts() == theme.load_fonts()


def test_sans_covers_russian_and_serif_is_for_latin_and_digits():
    theme.load_fonts()
    assert QFontDatabase.WritingSystem.Cyrillic in QFontDatabase.writingSystems(theme.SANS)
    # В Instrument Serif нет кириллицы: им набираются только цифры и латиница.
    assert QFontDatabase.WritingSystem.Cyrillic not in QFontDatabase.writingSystems(theme.SERIF)


def test_sans_is_set_tight_and_tighter_when_large():
    body, title, figure = (theme.sans_font(size).letterSpacing() for size in (14, 24, 150))
    assert theme.sans_font(14).letterSpacingType() == QFont.PercentageSpacing
    assert 95 <= body < 100
    assert figure < title <= body


def test_app_font_carries_the_tight_tracking():
    theme.apply(app)
    assert app.font().letterSpacingType() == QFont.PercentageSpacing
    assert 95 <= app.font().letterSpacing() < 100


def test_lists_and_combos_use_the_sans_not_the_windows_font():
    # Windows раздаёт спискам свой шрифт поверх шрифта приложения.
    theme.apply(app)
    for widget in (QListWidget(), QComboBox()):
        widget.show()
        app.processEvents()
        assert widget.font().family() == theme.SANS
        widget.close()


def test_placeholder_is_drawn_in_the_readable_colour():
    # Таблица стилей задаёт цвет текста, и без явного цвета подсказки Qt рисует её
    # этим цветом с половинной прозрачностью — 3,3:1 к заливке поля.
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLineEdit

    theme.apply(app)
    edit = QLineEdit()
    edit.setFocusPolicy(Qt.NoFocus)  # мигающий курсор чёрный и испортил бы замер
    edit.setPlaceholderText("видео или плейлист")
    edit.resize(260, 36)
    edit.show()
    app.processEvents()
    image = edit.grab().toImage()
    darkest = min(
        (image.pixelColor(x, y) for x in range(image.width()) for y in range(image.height())),
        key=lambda color: color.red() + color.green() + color.blue(),
    )
    edit.close()
    assert darkest.red() + darkest.green() + darkest.blue() <= 3 * 0x60


def _field_image():
    from PySide6.QtGui import QImage, QPainter

    image = QImage(290, 370, QImage.Format_RGB32)
    image.fill(0)
    painter = QPainter(image)
    theme.paint_field(painter, image.rect())
    painter.end()
    return image


def _average(image, top, bottom):
    pixels = [image.pixelColor(x, y) for x in range(0, image.width(), 5) for y in range(top, bottom, 5)]
    return [sum(getattr(p, channel)() for p in pixels) / len(pixels) for channel in ("red", "green", "blue")]


def test_field_is_cobalt_with_a_coral_glow():
    image = _field_image()
    red, green, blue = _average(image, 0, image.height())
    assert blue > 2 * max(red, green)  # глубокое синее поле
    corals = [image.pixelColor(x, y) for x in range(0, 290, 3) for y in range(0, 370, 3)]
    assert any(c.red() > 190 and c.blue() < 140 for c in corals)  # коралловое пятно есть


def test_light_text_stays_readable_on_the_calm_lower_left():
    # Внизу слева — «Hi.» и список загрузок: там должен быть тёмный кобальт, а не коралл.
    red, green, blue = _average(_field_image(), 250, 370)
    assert blue > 120 and red < 90


def test_text_is_smoothed_in_grey_without_cleartype_fringes():
    # ClearType оставляет синюю и оранжевую кайму у светлых букв на синем поле.
    theme.apply(app)
    for font in (app.font(), theme.sans_font(14), theme.figure_font(150), theme.serif_font(250)):
        assert font.styleStrategy() & QFont.NoSubpixelAntialias
        assert font.hintingPreference() == QFont.PreferNoHinting


def test_windows_text_goes_through_freetype_for_grey_smoothing():
    # DirectWrite и GDI рисуют ClearType даже при NoSubpixelAntialias; FreeType — серым.
    environ = {}
    theme.prefer_grey_text(environ, platform="win32")
    assert environ["QT_QPA_PLATFORM"] == "windows:fontengine=freetype"


def test_explicit_platform_choice_is_respected():
    environ = {"QT_QPA_PLATFORM": "offscreen"}
    theme.prefer_grey_text(environ, platform="win32")
    assert environ["QT_QPA_PLATFORM"] == "offscreen"
    other = {}
    theme.prefer_grey_text(other, platform="linux")
    assert other == {}
