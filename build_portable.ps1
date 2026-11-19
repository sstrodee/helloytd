# Сборка portable-версии: папка dist\helloytd, которая работает сама по себе —
# свой Python внутри, настройки и кэш в своей папке data, в системе ничего не остаётся.
# Запуск: powershell -ExecutionPolicy Bypass -File build_portable.ps1
param(
    [ValidatePattern('^helloytd(?:-[A-Za-z0-9]+)*$')][string]$OutputName = "helloytd"
)
$PythonVersion = "3.14.10"
$PythonZipSHA256 = "90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159"
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # иначе Invoke-WebRequest качает в разы медленнее

$root = $PSScriptRoot
$dist = Join-Path $root "dist"
$finalOut = Join-Path $dist $OutputName
$archive = Join-Path $dist "$OutputName-portable.zip"
if ((Test-Path -LiteralPath $finalOut) -or (Test-Path -LiteralPath $archive)) {
    throw "Сборка уже существует. Укажите свободное имя через -OutputName, чтобы сохранить её и пользовательские данные."
}
$staging = Join-Path $dist ("_build-" + [guid]::NewGuid().ToString("N"))
$out = Join-Path $staging "helloytd"
$runtime = Join-Path $out "runtime"
$site = Join-Path $runtime "Lib\site-packages"
$short = ($PythonVersion.Split(".")[0..1] -join "")

function Step($text) { Write-Host $text -ForegroundColor Cyan }
function Check($ok, $message) { if (-not $ok) { throw $message } }

$downloads = Join-Path $staging "_downloads"
$python = Join-Path $runtime "python.exe"

Step "1/7  Чистая папка $out"
New-Item -ItemType Directory -Force $runtime | Out-Null

Step "2/7  Встроенный Python $PythonVersion с python.org"
New-Item -ItemType Directory -Force $downloads | Out-Null
$zip = Join-Path $downloads "python-$PythonVersion-embed-amd64.zip"
if (-not (Test-Path $zip)) {
    Invoke-WebRequest "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip" -OutFile $zip -UseBasicParsing -TimeoutSec 60
}
Check ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash -eq $PythonZipSHA256) "Хэш архива Python не совпал."
Expand-Archive $zip $runtime
$signature = Get-AuthenticodeSignature (Join-Path $runtime "python$short.dll")
Check ($signature.Status -eq "Valid" -and $signature.SignerCertificate.Subject -like "*Python Software Foundation*") `
    "Подпись python$short.dll не прошла проверку — архив повреждён или подменён."
# Где искать модули: стандартная библиотека, site-packages и корень программы (там пакет app).
Set-Content (Join-Path $runtime "python$short._pth") -Encoding ASCII -Value @(
    "python$short.zip", ".", "Lib\site-packages", "..", "import site"
)

Step "3/7  pip и библиотеки (PySide6-Essentials, yt-dlp)"
# Системный Python не нужен: встроенный ставит себе pip официальным загрузчиком PyPA.
$getPip = Join-Path $downloads "get-pip.py"
if (-not (Test-Path $getPip)) {
    Invoke-WebRequest "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip -UseBasicParsing -TimeoutSec 60
}
& $python $getPip --quiet --no-cache-dir --disable-pip-version-check --no-warn-script-location
Check ($LASTEXITCODE -eq 0) "Не получилось поставить pip во встроенный Python."
& $python -m pip install --quiet --no-cache-dir --disable-pip-version-check --no-warn-script-location `
    -r (Join-Path $root "requirements.txt")
Check ($LASTEXITCODE -eq 0) "pip не смог поставить библиотеки."
& $python -m pip check
Check ($LASTEXITCODE -eq 0) "Несовместимые зависимости."
# pip.exe и прочие запускалки в Scripts помнят абсолютный путь — в переносимой папке бесполезны.
Remove-Item (Join-Path $runtime "Scripts") -Recurse -Force -ErrorAction SilentlyContinue

Step "4/7  Оставляю от Qt только то, что нужно окну"
$qt = Join-Path $site "PySide6"
$keepFiles = @(
    "Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll", "Qt6Svg.dll", "pyside6.abi3.dll",
    "QtCore.pyd", "QtGui.pyd", "QtWidgets.pyd", "QtSvg.pyd",
    "*140*.dll",                       # библиотеки Visual C++
    "*.py", "py.typed", "*.json"
)
$keepDirs = @("plugins", "support", "translations")
Get-ChildItem $qt -File | Where-Object { $name = $_.Name; -not ($keepFiles | Where-Object { $name -like $_ }) } |
    Remove-Item -Force
Get-ChildItem $qt -Directory | Where-Object { $keepDirs -notcontains $_.Name } | Remove-Item -Recurse -Force
$keepPlugins = @(
    "platforms\qwindows.dll", "styles\qmodernwindowsstyle.dll", "iconengines\qsvgicon.dll",
    "imageformats\qgif.dll", "imageformats\qico.dll", "imageformats\qjpeg.dll",
    "imageformats\qsvg.dll", "imageformats\qwebp.dll"
)
$plugins = Join-Path $qt "plugins"
Get-ChildItem $plugins -Recurse -File | Where-Object {
    $keepPlugins -notcontains $_.FullName.Substring($plugins.Length + 1)
} | Remove-Item -Force
Get-ChildItem $plugins -Directory | Where-Object { -not (Get-ChildItem $_.FullName -File) } | Remove-Item -Force
Get-ChildItem (Join-Path $qt "translations") -File | Where-Object { $_.Name -notin @("qtbase_ru.qm", "qt_ru.qm") } |
    Remove-Item -Force

Step "5/7  Код программы"
$appOut = Join-Path $out "app"
New-Item -ItemType Directory $appOut | Out-Null
Get-ChildItem (Join-Path $root "app") -File -Filter "*.py" | Copy-Item -Destination $appOut
Copy-Item (Join-Path $root "assets") $out -Recurse
Copy-Item (Join-Path $root "portable-readme.txt") (Join-Path $out "Прочти меня.txt")

Step "6/7  Значок и helloytd.exe"
$icon = Join-Path $out "assets\icon.ico"
& $python -B -c "import sys; from app.icon import write_ico; write_ico(sys.argv[1])" $icon
Check ($LASTEXITCODE -eq 0) "Не получилось нарисовать значок — встроенный Python или Qt не запускаются."
$csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
& $csc /nologo /target:winexe /platform:x64 /optimize+ /codepage:65001 `
    /reference:System.Windows.Forms.dll "/win32icon:$icon" "/out:$(Join-Path $out 'helloytd.exe')" `
    (Join-Path $root "launcher\Launcher.cs")
Check ($LASTEXITCODE -eq 0) "Не скомпилировался helloytd.exe."

Step "7/7  Проверка и архив"
& $python -B -c "import PySide6.QtWidgets, PySide6.QtSvg, yt_dlp, yt_dlp_ejs, pip, app.window; print('импорты в порядке')"
Check ($LASTEXITCODE -eq 0) "Собранная папка не запускается: не хватает модулей."
Add-Type -AssemblyName System.IO.Compression.FileSystem
$stagedArchive = Join-Path $staging "portable.zip"
[System.IO.Compression.ZipFile]::CreateFromDirectory(
    $out, $stagedArchive, [System.IO.Compression.CompressionLevel]::Optimal, $true)
[System.IO.Directory]::Move($out, $finalOut)
[System.IO.File]::Move($stagedArchive, $archive)
Remove-Item -LiteralPath $zip, $getPip
Remove-Item -LiteralPath $downloads, $staging
$out = $finalOut

$size = (Get-ChildItem $out -Recurse -File | Measure-Object Length -Sum).Sum / 1MB
Write-Host ""
Write-Host ("Готово: {0}  ({1:N0} МБ)" -f $out, $size) -ForegroundColor Green
Write-Host ("Архив:  {0}  ({1:N0} МБ)" -f $archive, ((Get-Item $archive).Length / 1MB)) -ForegroundColor Green
