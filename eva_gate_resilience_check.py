"""Проверка устойчивости фильтра: пауза после серии сбоев и запасная модель.

Сеть не нужна: подменяем сам вызов модели.
"""
import os
import sys
import importlib

os.environ.setdefault("HERMES_HOME", "/home/iizey/eva-home")
sys.path.insert(0, "/home/iizey/eva-hermes")

gate = importlib.import_module("plugins.platforms.telegram.eva_gate")

fail = []


def check(name, cond, extra=""):
    print(f"[{'ok' if cond else 'FAIL'}] {name}{' — ' + str(extra) if extra else ''}")
    if not cond:
        fail.append(name)


def reset():
    gate._STATE["failures"] = 0.0
    gate._STATE["cooldown_until"] = 0.0


CHAT = (["[Алексей] ты дебил, Паша", "[Паша] сам такой"], "[Паша] сам такой")

# 1. Основной провайдер лежит, запасной отвечает -> вердикт есть
reset()
calls = []


def fake_call(base, key, model, messages, **kw):
    """Основная модель «лежит» (None), запасная отвечает ДА."""
    calls.append(model)
    return None if "nemotron" in model else "ДА"


gate._call = fake_call
verdict = gate.should_reply(*CHAT)
check("при сбое основного вызвана запасная модель", len(calls) == 2, calls)
check("вердикт взят у запасной модели", verdict is True, verdict)
check("счётчик сбоев сброшен после успеха", gate._STATE["failures"] == 0, gate._STATE)

# 2. Обе модели лежат: три сбоя подряд -> фильтр уходит на паузу
reset()
calls.clear()
gate._call = lambda *a, **kw: (calls.append("try"), None)[1]
for _ in range(3):
    check_verdict = gate.should_reply(*CHAT)
check("при полном отказе вердикта нет", check_verdict is None, check_verdict)
check("пауза включилась", gate._STATE["cooldown_until"] > 0, gate._STATE)
before = len(calls)
instant = gate.should_reply(*CHAT)
check("на паузе модель не дёргается", len(calls) == before, (before, len(calls)))
check("на паузе тоже нет решения", instant is None, instant)

# 3. Пауза кончилась -> снова пробуем
reset()
gate._call = fake_call
check("после сброса паузы фильтр снова работает", gate.should_reply(*CHAT) is True)

print("\nGATE-RESILIENCE", "PASSED" if not fail else f"FAILED: {fail}")
sys.exit(1 if fail else 0)
