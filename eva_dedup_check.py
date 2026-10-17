"""Проверка дедупа дневника: та же тема → дописываем, копия чужой записи → отказ.

Работает на временном дневнике (HERMES_HOME подменяется до импорта eva_memory).
"""
import os
import shutil
import sys
from pathlib import Path

TMP = Path("/home/iizey/.hermes/cache/scratch/eva-mem-test-dedup")
shutil.rmtree(TMP, ignore_errors=True)
(TMP / "diary" / "алексей").mkdir(parents=True)
os.environ["HERMES_HOME"] = str(TMP)
sys.path.insert(0, "/home/iizey/eva-hermes")

BODY_OLD = ("Алексей сегодня опять наехал: сказал, что я тупая. Я ответила, что сам такой. "
            "Он вечно начинает первый, с ним надо держать ухо востро.")
(TMP / "diary" / "алексей" / "SKILL.md").write_text(
    f"---\nname: алексей\ndescription: хамит\n---\n{BODY_OLD}\n", encoding="utf-8")

from tools.skill_manager_tool import _diary_dedup  # noqa: E402

fail = []


def check(name, cond, extra=""):
    print(f"[{'ok' if cond else 'FAIL'}] {name}{' — ' + str(extra) if extra else ''}")
    if not cond:
        fail.append(name)


def page(name, body):
    return f"---\nname: {name}\ndescription: запись\n---\n{body}\n"


# 1. Та же тема (то же имя): должна быть дописана в существующую страницу
out = _diary_dedup("Алексей", page("Алексей", "Опять довёл меня сегодня, пришлось ответить грубо."))
check("та же тема -> дописывание", bool(out) and out.get("success") is True, out)
text = (TMP / "diary" / "алексей" / "SKILL.md").read_text(encoding="utf-8")
check("старый текст на месте", "держать ухо востро" in text)
check("новый текст дописан", "пришлось ответить грубо" in text)
check("вторая страница не создалась", sorted(p.name for p in (TMP / "diary").iterdir()) == ["алексей"],
      sorted(p.name for p in (TMP / "diary").iterdir()))

# 2. Другая тема, но текст — почти копия: отказ, называющий существующую страницу
out = _diary_dedup("Ссора в чате", page("Ссора в чате", BODY_OLD))
check("копия чужой записи -> отказ", bool(out) and out.get("success") is not True, out)
check("в отказе названа страница", bool(out) and "алексей" in str(out), out)

# 3. Новая тема с новым текстом — писать можно
out = _diary_dedup("кошки", page("кошки", "Листала полночи видосы с котятами, уличный кот — событие дня."))
check("новое про другое -> можно писать", out is None, out)

# 4. Короткая приписка не сравнивается
out = _diary_dedup("кошки", page("кошки", "ну да"))
check("короткая приписка -> можно писать", out is None, out)

print("\nDEDUP", "PASSED" if not fail else f"FAILED: {fail}")
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if fail else 0)
