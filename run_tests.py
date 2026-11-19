r"""Тесты на Python из portable-сборки — системный Python не нужен.

    dist\helloytd\runtime\python.exe run_tests.py

При первом запуске ставит pytest в папку .test-deps рядом с проектом.
"""

import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
DEPS = PROJECT / ".test-deps"

if not (DEPS / "pytest").is_dir():
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet", "--no-cache-dir",
         "--disable-pip-version-check", "--target", str(DEPS), "pytest"],
        check=True,
    )
# Исходники проекта — раньше копии app из сборки, которая тоже лежит в путях.
sys.path[:0] = [str(DEPS), str(PROJECT)]
sys.dont_write_bytecode = True

import pytest  # noqa: E402

# Временные файлы тестов — в .test-deps, а не в %TEMP%: pytest чистит их сам при каждом запуске.
sys.exit(pytest.main([
    str(PROJECT / "tests"), "-q", "-W", "error", "-p", "no:cacheprovider",
    f"--basetemp={DEPS / 'tmp'}", *sys.argv[1:],
]))
