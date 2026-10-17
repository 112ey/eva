"""Проверка фильтра «звать ли Еву» на живом провайдере (та же модель, что у неё).

Показывает вердикт модели по нескольким типовым ситуациям чата.
"""
import os
import sys

os.environ.setdefault("HERMES_HOME", "/home/iizey/eva-home")
sys.path.insert(0, "/home/iizey/eva-hermes")

from plugins.platforms.telegram.eva_gate import resolve_target, should_reply  # noqa: E402

CASES = [
    ("болтовня не про неё", ["[Паша] кто-нибудь видел мой зарядник?"], False),
    ("ссора", ["[Алексей] ты дебил, Паша", "[Паша] сам такой, иди отсюда"], True),
    ("мемы и смех", ["[Паша] вот мем", "[Максим] ахахах", "[Алексей] лол"], False),
    ("говорят про неё", ["[Паша] Ева вообще чё-то притихла", "[Максим] ага, молчит"], True),
    ("важная новость", ["[Максим] у меня вчера кот умер"], True),
    ("планы на завтра", ["[Алексей] во сколько собираемся завтра?", "[Паша] часа в два"], False),
]

provider, model, base_url = resolve_target()
print(f"фильтр на модели: {model!r} (провайдер {provider!r}, base_url={base_url!r})\n")

mismatch = []
for name, history, expected in CASES:
    verdict = should_reply(history, history[-1])
    mark = "ok " if verdict is expected else "!! "
    print(f"[{mark}] {name}: вердикт={verdict!r} (ждали {expected!r})")
    if verdict is not expected:
        mismatch.append(name)

print("\nGATE", "PASSED" if not mismatch else f"РАСХОЖДЕНИЯ: {mismatch}")
