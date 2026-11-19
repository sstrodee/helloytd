"""Тексты интерфейса: без обращения к пользователю, без болтовни от первого лица, без «·».

Проверяются все строки в коде приложения, кроме docstring'ов: подпись, ошибка
или подсказка, добавленная завтра, попадёт под ту же проверку.
"""

import ast
import re
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parent.parent / "app"

ADDRESS = re.compile(
    r"(?<![а-яё])(ты|тебя|тебе|тобой|твой|твоя|твоё|твои|твоего|твоей|твоим|"
    r"вы|вас|вам|вами|ваш|ваша|ваше|ваши|вашего|вашей)(?![а-яё])",
    re.IGNORECASE,
)
# Повелительное наклонение, обращённое к человеку.
IMPERATIVE = re.compile(
    r"(?<![а-яё])(вставь|установи|нажми|включи|выбери|войди|попробуй|проверь|обнови|подожди|"
    r"перезапусти|скопируй|укажи|открой|закрой|смени|зайди)(?![а-яё])",
    re.IGNORECASE,
)
# Программа не рассказывает о себе: «проверяю», «скачиваю», «сделаю сам».
FIRST_PERSON = re.compile(
    r"(?<![а-яё])(проверяю|ищу|открываю|скачиваю|останавливаю|обновляю|готовлю|склеиваю|"
    r"вырезаю|конвертирую|записываю|встраиваю|пробую|сделаю)(?![а-яё])",
    re.IGNORECASE,
)


def _docstrings(tree):
    nodes = [tree] + [node for node in ast.walk(tree)
                      if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    found = set()
    for node in nodes:
        body = getattr(node, "body", [])
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            found.add(id(body[0].value))
    return found


def _strings():
    for path in sorted(APP.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        skip = _docstrings(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
                yield f"{path.name}:{node.lineno}", node.value


STRINGS = list(_strings())


def test_strings_were_found():
    assert len(STRINGS) > 100


@pytest.mark.parametrize("pattern,what", [
    (ADDRESS, "обращение на ты или вы"),
    (IMPERATIVE, "повелительное наклонение"),
    (FIRST_PERSON, "первое лицо"),
])
def test_copy_does_not_talk_to_the_user(pattern, what):
    offenders = [f"{where}: {text!r}" for where, text in STRINGS if pattern.search(text)]
    assert not offenders, f"{what}:\n" + "\n".join(offenders)


def test_no_middle_dots():
    offenders = [f"{where}: {text!r}" for where, text in STRINGS if "·" in text]
    assert not offenders, "\n".join(offenders)
