"""Проверка рабочей памяти: промт, запись файла, откат на мусорный ответ модели."""
import importlib.util
import os
import shutil
import sys
from pathlib import Path

TMP = Path("/home/iizey/.hermes/cache/scratch/eva-mem-test-wm")
shutil.rmtree(TMP, ignore_errors=True)
(TMP / "diary").mkdir(parents=True)
os.environ["HERMES_HOME"] = str(TMP)
sys.path.insert(0, "/home/iizey/eva-hermes")

(TMP / "diary" / "алексей" / "SKILL.md").parent.mkdir(parents=True)
(TMP / "diary" / "алексей" / "SKILL.md").write_text(
    "---\nname: алексей\ndescription: хамит\n---\nАлексей довёл меня сегодня, пришлось ответить грубо.\n",
    encoding="utf-8")

import eva_memory  # noqa: E402
spec = importlib.util.spec_from_file_location("eval_wm", "/home/iizey/eva-home/working_memory.py")
wm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wm)

fail = []


def check(name, cond, extra=""):
    print(f"[{'ok' if cond else 'FAIL'}] {name}{' — ' + str(extra) if extra else ''}")
    if not cond:
        fail.append(name)


# 1. Промт: первая сборка без прошлой памяти + дневник подмешан
prompt = wm.build("", "[Паша] Ева, напомни мне про зарядник", "Алексей довёл меня сегодня.")
check("пустая память помечена как первая сборка", "первая сборка" in prompt)
check("свежие сообщения в промте", "зарядник" in prompt)
check("дневник в промте", "Алексей довёл" in prompt)
check("требование дат на месте", "последнее обновление" in prompt)

# 2. Запись файла + бэкап прошлой версии
wm.call_model = lambda prompt, **_: ("- Напомнить Паше про зарядник — последнее обновление: 16 окт\n"
                                     "- Настроение: спокойное\n- Самочувствие: выспалась")
sys.argv = ["working_memory.py", "--apply"]
code = wm.main()
check("сборка завершилась успешно", code == 0, code)
check("файл создан", eva_memory.WORKING_MEMORY.exists(), eva_memory.WORKING_MEMORY)
block = eva_memory.working_memory_block()
check("блок <things_to_remember> собирается", block.startswith("<things_to_remember>") and "зарядник" in block,
      block[:80])

sys.argv = ["working_memory.py", "--apply"]
wm.main()
check("прошлая версия сохранена в .bak", eva_memory.WORKING_MEMORY.with_suffix(".md.bak").exists())

# 3. Мусорный ответ модели не перезаписывает память
before = eva_memory.read_working_memory()
wm.call_model = lambda prompt, **_: "ок"
sys.argv = ["working_memory.py", "--apply"]
code = wm.main()
check("короткий ответ отброшен", code == 1, code)
check("память не пострадала", eva_memory.read_working_memory() == before)

print("\nWORKING-MEMORY", "PASSED" if not fail else f"FAILED: {fail}")
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if fail else 0)
