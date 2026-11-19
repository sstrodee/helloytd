# helloytd third-party notices

[Русский](#сторонние-компоненты-helloytd)

helloytd uses Qt 6.12.0, PySide6 Essentials 6.12.0, and Shiboken6 6.12.0 under the GNU LGPL version 3. The portable ZIP contains the full [LGPL 3](licenses/LGPL-3.0-only.txt) and [GPL 3](licenses/GPL-3.0-only.txt) license texts.

The app loads these libraries separately from `runtime\Lib\site-packages`. To replace Qt and PySide6, close helloytd, make a copy of the portable folder, and replace the libraries and plug-ins with compatible Windows x64 builds. The helloytd license allows library replacement and reverse engineering to debug those changes. The build script selects a subset of Qt modules and uses their binaries as provided by the official packages.

## Sources and licenses for Windows x64

| Component | Bundled version and materials |
| --- | --- |
| Qt for Python / Shiboken | [6.12.0 source and download information](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.12.0-src/), [component licenses](https://doc.qt.io/qtforpython-6/licenses.html) |
| Qt Core, Gui, Widgets, Svg, and image plug-ins | [Qt 6.12.0 source](https://download.qt.io/archive/qt/6.12/6.12.0/submodules/) in the `qtbase`, `qtsvg`, `qtimageformats`, and `qttranslations` archives. [Qt licenses](https://doc.qt.io/qt-6/licenses-used-in-qt.html) |
| CPython | [3.14.10 source](https://www.python.org/downloads/release/python-31410/). License and notices are in `runtime/LICENSE.txt` |
| yt-dlp and yt-dlp-ejs | [yt-dlp 2026.10.26](https://pypi.org/project/yt-dlp/2026.10.26/#files), [yt-dlp-ejs 0.8.0](https://pypi.org/project/yt-dlp-ejs/0.8.0/#files) |
| Mutagen | [1.48.1 source](https://pypi.org/project/mutagen/1.48.1/#files), GPL 2.0 or later |
| Other Python packages | Versions and licenses are in `runtime/Lib/site-packages/*-*.dist-info`. [PyPI](https://pypi.org/) provides source packages for these versions |
| Golos Text and Instrument Serif | SIL Open Font License 1.1. The license texts are in [assets/fonts](assets/fonts/) |

Install FFmpeg, Node.js, or Deno separately as needed.

## Сторонние компоненты helloytd

Приложение использует библиотеки Qt 6.12.0, PySide6 Essentials 6.12.0 и Shiboken6 6.12.0 под GNU LGPL версии 3. Полные тексты [LGPL 3](licenses/LGPL-3.0-only.txt) и [GPL 3](licenses/GPL-3.0-only.txt) включены в portable ZIP.

Библиотеки загружаются отдельно из `runtime\Lib\site-packages`. Для замены Qt и PySide6 можно закрыть приложение, сделать копию portable-папки и заменить библиотеки и плагины совместимыми Windows x64 сборками этих компонентов. Условия helloytd не ограничивают замену библиотек и обратный анализ, необходимый для отладки таких изменений. Скрипт сборки сокращает набор поставляемых модулей Qt, сохраняя сами двоичные файлы из официальных пакетов.

### Исходники и лицензии для Windows x64

| Компонент | Поставляемая версия и материалы |
| --- | --- |
| Qt for Python / Shiboken | [Исходники 6.12.0 и сведения о загрузке](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.12.0-src/), [лицензии компонентов](https://doc.qt.io/qtforpython-6/licenses.html) |
| Qt Core, Gui, Widgets, Svg и плагины изображений | [Исходники Qt 6.12.0](https://download.qt.io/archive/qt/6.12/6.12.0/submodules/) в архивах `qtbase`, `qtsvg`, `qtimageformats`, `qttranslations`. [Лицензии Qt](https://doc.qt.io/qt-6/licenses-used-in-qt.html) |
| CPython | [Исходники 3.14.10](https://www.python.org/downloads/release/python-31410/). Лицензия и уведомления лежат в `runtime/LICENSE.txt` |
| yt-dlp и yt-dlp-ejs | [yt-dlp 2026.10.26](https://pypi.org/project/yt-dlp/2026.10.26/#files), [yt-dlp-ejs 0.8.0](https://pypi.org/project/yt-dlp-ejs/0.8.0/#files) |
| Mutagen | [Исходники 1.48.1](https://pypi.org/project/mutagen/1.48.1/#files), GPL 2.0 или более поздняя версия |
| Остальные пакеты Python | Версии и тексты лицензий сохранены в `runtime/Lib/site-packages/*-*.dist-info`. [PyPI](https://pypi.org/) предоставляет исходники пакетов по этим версиям |
| Golos Text и Instrument Serif | SIL Open Font License 1.1. Тексты лицензий находятся в [assets/fonts](assets/fonts/) |

FFmpeg, Node.js и Deno устанавливаются отдельно и в архив helloytd не входят.
