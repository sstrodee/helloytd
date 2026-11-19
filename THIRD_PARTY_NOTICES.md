# Сторонние компоненты helloytd

Приложение использует библиотеки Qt 6.12.0, PySide6 Essentials 6.12.0 и Shiboken6 6.12.0 под GNU LGPL версии 3. Полные тексты [LGPL 3](licenses/LGPL-3.0-only.txt) и [GPL 3](licenses/GPL-3.0-only.txt) включены в portable ZIP.

Библиотеки загружаются отдельно из `runtime\Lib\site-packages`. Для замены Qt и PySide6 можно закрыть приложение, сделать копию portable-папки и заменить библиотеки и плагины совместимыми Windows x64 сборками этих компонентов. Условия helloytd не ограничивают замену библиотек и обратный анализ, необходимый для отладки таких изменений. Скрипт сборки сокращает набор поставляемых модулей Qt, сохраняя сами двоичные файлы из официальных пакетов.

## Исходники и лицензии для Windows x64 1.0.0

| Компонент | Поставляемая версия и материалы |
| --- | --- |
| Qt for Python / Shiboken | [Исходники 6.12.0 и сведения о загрузке](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.12.0-src/), [лицензии компонентов](https://doc.qt.io/qtforpython-6/licenses.html) |
| Qt Core, Gui, Widgets, Svg и плагины изображений | [Исходники Qt 6.12.0](https://download.qt.io/archive/qt/6.12/6.12.0/submodules/) в архивах `qtbase`, `qtsvg`, `qtimageformats`. [Лицензии Qt](https://doc.qt.io/qt-6/licenses-used-in-qt.html) |
| CPython | [Исходники 3.14.10](https://www.python.org/downloads/release/python-31410/). Лицензия и уведомления лежат в `runtime/LICENSE.txt` |
| yt-dlp и yt-dlp-ejs | [yt-dlp 2026.10.26](https://pypi.org/project/yt-dlp/2026.10.26/#files), [yt-dlp-ejs 0.8.0](https://pypi.org/project/yt-dlp-ejs/0.8.0/#files) |
| Mutagen | [Исходники 1.48.1](https://pypi.org/project/mutagen/1.48.1/#files), GPL 2.0 или более поздняя версия |
| Остальные пакеты Python | Версии и тексты лицензий сохранены в `runtime/Lib/site-packages/*-*.dist-info`. [PyPI](https://pypi.org/) предоставляет исходники пакетов по этим версиям |
| Golos Text и Instrument Serif | SIL Open Font License 1.1. Тексты лицензий находятся в [assets/fonts](assets/fonts/) |

FFmpeg, Node.js и Deno устанавливаются отдельно и в архив helloytd не входят.
