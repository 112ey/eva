"""Проверка «сна»: слияние похожих страниц, безопасность, бэкап — на временном дневнике."""
import os
import shutil
import sys
import random
from pathlib import Path

TMP = Path("/home/iizey/.hermes/cache/scratch/eva-mem-test-sleep")
shutil.rmtree(TMP, ignore_errors=True)
(TMP / "diary").mkdir(parents=True)
os.environ["HERMES_HOME"] = str(TMP)
sys.path.insert(0, "/home/iizey/eva-hermes")

PAGES = {
    "алексей": "Алексей сегодня опять наехал: сказал, что я тупая. Я ответила, что сам такой. "
             "Он вечно начинает первый, с ним надо держать ухо востро.",
    "алексей-2": "Алексей опять начал про своё и довёл. Пришлось ответить ему грубо. "
               "Он первый начал, я не собираюсь терпеть такое.",
    "кошки": "Люблю кошек. Листала видосы с котятами полночи, уличный кот во дворе — событие дня.",
}


def write_pages():
    """Пишем страницы с явными временами: новейшая — про Алексея (её и выберет «сон»)."""
    stamps = {"кошки": 1000, "алексей": 2000, "алексей-2": 3000}
    for name, body in PAGES.items():
        d = TMP / "diary" / name
        d.mkdir(parents=True, exist_ok=True)
        f = d / "SKILL.md"
        f.write_text(f"---\nname: {name}\ndescription: запись\n---\n{body}\n", encoding="utf-8")
        os.utime(f, (stamps[name], stamps[name]))


write_pages()
import eva_memory  # noqa: E402
import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location("eva_sleep", "/home/iizey/eva-home/sleep.py")
sleep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sleep)

fail = []


def check(name, cond, extra=""):
    print(f"[{'ok' if cond else 'FAIL'}] {name}{' — ' + str(extra) if extra else ''}")
    if not cond:
        fail.append(name)


MERGED = ("Алексей вечно начинает первым и хамит — сегодня опять сказал, что я тупая, "
          "и я ответила грубо. Терпеть такое не собираюсь.")


def run(apply=True, fake=MERGED, **kw):
    write_pages()
    sleep.call_model = lambda prompt, **_: fake
    params = dict(apply=apply, rng=random.Random(7), max_merges=2, max_minutes=5,
                  min_similarity=0.18, skip_recent_hours=0)
    params.update(kw)
    return sleep.sleeping(eva_memory.diary_pages(), **params)


# 1. Нормальное слияние: похожие записи про Алексея сливаются в одну, кошки не тронуты
from eva_memory import similarity as _sim  # noqa: E402
print(f"[i] близость двух записей про Алексея: {_sim(PAGES['алексей'], PAGES['алексей-2']):.2f}")
run(apply=True)
pages = {p.name: p for p in eva_memory.diary_pages()}
check("осталась одна запись про Алексея", sum(1 for n in pages if "алексей" in n) == 1, list(pages))
check("запись про кошек не тронута", "кошки" in pages)
kept = pages.get("алексей") or pages.get("алексей-2")
check("текст — результат слияния", kept and "начинает первым" in kept.body, kept.body[:60] if kept else "")
check("шапка страницы сохранена", kept and kept.description == "запись", kept.description if kept else "")
backups = list((TMP / "diary_backups").glob("sleep_*/*/SKILL.md"))
check("бэкап слитых страниц сделан", len(backups) >= 2, [str(b) for b in backups])

# 2. Слишком короткий ответ модели — ничего не меняем и не удаляем
try:
    run(apply=True, fake="ну и ладно")
except Exception as exc:
    check("короткий ответ не роняет сон", False, exc)
else:
    left = [p.name for p in eva_memory.diary_pages()]
    check("короткий ответ оставляет все страницы", len(left) == 3, left)

# 3. Разросшийся ответ — тоже мимо (защита от выдумывания)
run(apply=True, fake="Алексей " * 2000)
left = [p.name for p in eva_memory.diary_pages()]
check("разросшийся ответ не применяется", len(left) == 3, left)

# 4. dry-run ничего не пишет и не удаляет
run(apply=False)
left = [p.name for p in eva_memory.diary_pages()]
check("dry-run без изменений", len(left) == 3, left)

print("\nSLEEP", "PASSED" if not fail else f"FAILED: {fail}")
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if fail else 0)
