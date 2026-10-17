"""Проверка, что прочитанная болтовня доходит до модели как контекст, а не как просьба.

Берём настоящие функции гейтвея: _build_gateway_agent_history + _wrap_current_message_with_observed_context.
"""
import os
import sys

os.environ.setdefault("HERMES_HOME", "/home/iizey/eva-home")
sys.path.insert(0, "/home/iizey/eva-hermes")

from gateway.run import (  # noqa: E402
    _CURRENT_ADDRESSED_MESSAGE_HEADER,
    _OBSERVED_GROUP_CONTEXT_HEADER,
    _TELEGRAM_OBSERVED_CONTEXT_PROMPT_MARKER,
    _build_gateway_agent_history,
    _wrap_current_message_with_observed_context,
)

fail: list[str] = []


def check(name, cond, extra=""):
    print(f"[{'ok' if cond else 'FAIL'}] {name}{' — ' + str(extra) if extra else ''}")
    if not cond:
        fail.append(name)


HISTORY = [
    {"role": "user", "content": "[Паша|111] кто-нибудь видел мой зарядник?", "observed": True},
    {"role": "assistant", "content": "не видела"},
    {"role": "user", "content": "[Паша|111] Ева вообще чтихла", "observed": True},
    {"role": "user", "content": "[Владелец|222] Ева, ты тут?"},
]

# Такой промт адаптер подкладывает групповым ходам (см. _telegram_group_observe_channel_prompt).
prompt = ("You are handling a Telegram group chat message.\n"
          f"- {_TELEGRAM_OBSERVED_CONTEXT_PROMPT_MARKER} may be provided in a separate block.")
check("маркер наблюдения в промте распознан", _TELEGRAM_OBSERVED_CONTEXT_PROMPT_MARKER in prompt)

agent_history, observed = _build_gateway_agent_history(HISTORY, channel_prompt=prompt)
texts = [m.get("content") for m in agent_history if isinstance(m.get("content"), str)]
check("адресованное сообщение осталось ходом", any("Ева, ты тут?" in t for t in texts))
check("наблюдаемая болтовня НЕ идёт как реплика", not any("зарядник" in t for t in texts), texts)
check("наблюдаемая болтовня попала в отдельный контекст",
      bool(observed) and "зарядник" in observed and "чтихла" in observed, repr(observed)[:120])

wrapped = _wrap_current_message_with_observed_context("Ева, ты тут?", observed)
joined = wrapped if isinstance(wrapped, str) else "\n".join(
    part.get("text", "") for part in wrapped if isinstance(part, dict))
check("контекст приклеен к текущему сообщению", _OBSERVED_GROUP_CONTEXT_HEADER in joined, joined[:160])
check("текущее сообщение помечено как адресованное", _CURRENT_ADDRESSED_MESSAGE_HEADER in joined)

# Без маркера (не тот промт) болтовня всё равно не теряется — уходит обычной историей.
agent_history2, observed2 = _build_gateway_agent_history(HISTORY, channel_prompt=None)
texts2 = [m.get("content") for m in agent_history2 if isinstance(m.get("content"), str)]
check("без маркера болтовня остаётся в истории (не теряется)", any("зарядник" in t for t in texts2))
check("без маркера отдельного блока нет", observed2 is None, repr(observed2)[:60])

print("\nCONTEXT", "PASSED" if not fail else f"FAILED: {fail}")
sys.exit(1 if fail else 0)
