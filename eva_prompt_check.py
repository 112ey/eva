"""Проверка, что память доехала до промта и до сообщения.

Три вещи: блок рабочей памяти в промте, правило про <вспомнилось>, и подклейка воспоминаний
к реальному сообщению (на настоящем MessageEvent и настоящем дневнике).
"""
import os
import sys
import types
import dataclasses

os.environ.setdefault("HERMES_HOME", "/home/iizey/eva-home")
sys.path.insert(0, "/home/iizey/eva-hermes")

from agent import system_prompt as sp  # noqa: E402
from gateway.platforms.event import MessageEvent, MessageType  # noqa: E402
from gateway.session import SessionSource  # noqa: E402
from plugins.platforms.telegram.adapter import TelegramAdapter  # noqa: E402

fail = []


def check(name, cond, extra=""):
    print(f"[{'ok' if cond else 'FAIL'}] {name}{' — ' + str(extra) if extra else ''}")
    if not cond:
        fail.append(name)


class FakeAgent:
    valid_tool_names = {"skills_list", "skill_view", "skill_manage"}


# 1. Рабочая память в промте
part = sp._working_memory_part(FakeAgent())
check("блок «Что нельзя забыть» есть", "## Что нельзя забыть" in part)
check("рабочая память подставлена", "<things_to_remember>" in part, part[-160:].replace("\n", " ")[:120])

# 2. Правило про <вспомнилось> в дневниковой части
ritual = sp._diary_ritual_part(FakeAgent())
check("промт знает про <вспомнилось>", "<вспомнилось>" in ritual)

# 3. Воспоминания реально подклеиваются к сообщению
event = MessageEvent(
    source=SessionSource(platform="telegram", chat_id="-1002222222222", chat_type="group",
                         user_id="111111111", user_name="Владелец"),
    text="слушай, а что там у Алексея вообще было?",
    message_type=MessageType.TEXT,
)
# Заглушка адаптера: методы, которые зовёт _eva_attach_recall, берём у настоящего класса — иначе
# после добавления блока «кто пишет» заглушка без них падает.
stub = types.SimpleNamespace(name="Telegram")
stub._eva_attach_people = lambda event: event
attached = TelegramAdapter._eva_attach_recall(stub, event)
check("к сообщению добавлен блок воспоминаний", "<вспомнилось>" in (attached.text or ""),
      (attached.text or "")[:200].replace("\n", " "))
check("исходный текст не потерян", "у Алексея" in (attached.text or ""))
check("в блоке названа конкретная страница дневника", "• " in (attached.text or ""),
      (attached.text or "")[-90:].replace("\n", " "))

# 4. Нечего вспомнить — сообщение не меняется
boring = dataclasses.replace(event, text="привет")
same = TelegramAdapter._eva_attach_recall(stub, boring)
check("без совпадений ничего не добавляется", same.text == "привет", same.text)

# 5. Команды не трогаем
cmd = dataclasses.replace(event, message_type=MessageType.COMMAND, text="/status")
check("команда остаётся командой", TelegramAdapter._eva_attach_recall(stub, cmd).text == "/status")

print("\nMEMORY-WIRING", "PASSED" if not fail else f"FAILED: {fail}")
sys.exit(1 if fail else 0)
