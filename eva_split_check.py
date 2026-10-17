"""Проверка дробления ответа: маркер «[[|]]» → несколько отдельных сообщений."""
import asyncio
import sys
import time
import types

sys.path.insert(0, "/home/iizey/eva-hermes")
sys.path.insert(0, "/home/iizey/eva-home")

import plugins.platforms.telegram.adapter as adapter_mod  # noqa: E402
from plugins.platforms.telegram.adapter import TelegramAdapter  # noqa: E402

fail = []


def check(name, cond, extra=""):
    print(f"[{'ok' if cond else 'FAIL'}] {name}{' — ' + str(extra) if extra else ''}")
    if not cond:
        fail.append(name)


class _Stub(TelegramAdapter):
    name = "Telegram"

    def __init__(self, delay=0.0, max_parts=4):
        self.config = types.SimpleNamespace(extra={"eva_split_max_parts": max_parts,
                                                  "eva_split_delay_seconds": delay})
        self.sent = []

    # окружение send(): всё лишнее — заглушки
    def _eva_muted(self):
        return False

    def _eva_apply_topic_marker(self, chat_id, content, metadata):
        return content, metadata

    def _eva_split_reaction_marker(self, content):
        return content, ""

    def _eva_resolve_sticker_marker(self, content):
        return content, None

    def _eva_style(self, content):
        return content

    def _eva_meta_blocked(self, content):
        return False

    def _eva_note_own_message(self, chat_id, content):
        return None

    async def _send_text_locked(self, chat_id, content, reply_to=None, metadata=None):
        self.sent.append((content, reply_to))
        return types.SimpleNamespace(success=True, message_id=str(len(self.sent)))

    def _chat_send_lock(self, chat_id):
        return _null_lock()

    def _eva_attach_recall(self, event):
        return event


class _null_lock:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc):
        return False


stub = object.__new__(_Stub)
_Stub.__init__(stub)
stub._bot = types.SimpleNamespace()

# 1. Разбор маркера
cases = [
    ("одна мысль", ["одна мысль"]),
    ("привет[[|]]как дела", ["привет", "как дела"]),
    ("привет\n[[|]]\nкак дела", ["привет", "как дела"]),
    ("раз[[|]]два[[|]]три", ["раз", "два", "три"]),
    ("а[[|]][[|]]б", ["а", "б"]),
    ("раз[[разрыв]]два", ["раз", "два"]),
    ("", []),
    ("[[|]]", []),
]
for text, want in cases:
    got = TelegramAdapter._eva_split_parts(stub, text)
    check(f"разбор {text!r}", got == want, got)

# 2. Потолок частей: лишние склеиваются в последнюю
stub.config.extra["eva_split_max_parts"] = 3
got = TelegramAdapter._eva_split_parts(stub, "а[[|]]б[[|]]в[[|]]г[[|]]д")
check("частей не больше потолка", len(got) == 3 and got[-1] == "в\nг\nд", got)
stub.config.extra["eva_split_max_parts"] = 4

# 3. Через send(): каждая часть — отдельное сообщение, якорь только у первой
asyncio.run(TelegramAdapter.send(stub, "-1001111111111", "привет[[|]]как дела[[|]]чё делаешь", reply_to="42"))
check("три части → три сообщения", len(stub.sent) == 3, stub.sent)
check("текст частей правильный", [t for t, _ in stub.sent] == ["привет", "как дела", "чё делаешь"], stub.sent)
check("реплай-якорь только у первой", [r for _, r in stub.sent] == ["42", None, None], stub.sent)

# 4. Одна мысль — одно сообщение (ничего не меняется)
stub.sent.clear()
asyncio.run(TelegramAdapter.send(stub, "-1001111111111", "одна мысль"))
check("без маркера одно сообщение", stub.sent == [("одна мысль", None)], stub.sent)

# 5. Пауза между частями реально есть
stub.sent.clear()
stub.config.extra["eva_split_delay_seconds"] = 0.2
started = time.monotonic()
asyncio.run(TelegramAdapter.send(stub, "-1001111111111", "раз[[|]]два[[|]]три"))
elapsed = time.monotonic() - started
check("между частями есть пауза (как будто печатает)", elapsed >= 0.2, f"{elapsed:.2f}с")
stub.config.extra["eva_split_delay_seconds"] = 0.0

# 6. Если сообщение начинается с маркера реакции — реакция ставится, а дробление не ломается
stub.sent.clear()
reacted = []
_calls = {"n": 0}


def _reaction_once(content):
    """Маркер снимается только с первого (целого) сообщения — как в жизни."""
    _calls["n"] += 1
    if _calls["n"] == 1 and "[[реакция" in content:
        return content.replace("[[реакция: 🔥]]", "").strip(), "🔥"
    return content, ""


stub._eva_split_reaction_marker = _reaction_once
stub._eva_react_to_last = lambda chat_id, emoji: reacted.append(emoji) or asyncio.sleep(0)
asyncio.run(TelegramAdapter.send(stub, "-1001111111111", "[[реакция: 🔥]] и вот ещё[[|]]и второе"))
check("реакция ставится вместе с дроблением", reacted == ["🔥"], reacted)
stub._eva_split_reaction_marker = lambda content: (content, "")

# 7. Сквозная проверка таймера: тот же маркер понимает send_local
import send_local  # noqa: E402

parts = send_local.split_parts("первое[[|]]второе[[|]]третье")
check("таймер тоже дробит", parts == ["первое", "второе", "третье"], parts)
check("таймер уважает потолок", send_local.split_parts("а[[|]]б[[|]]в[[|]]г[[|]]д", max_parts=2) == ["а", "б"], None)
check("таймер без маркера шлёт одним", send_local.split_parts("просто текст") == ["просто текст"])

# 8. В промт попадает объяснение маркера
block = TelegramAdapter._eva_split_prompt(stub)
check("в промте есть объяснение дробления", "[[|]]" in block and "3–4 частей" in block, block[:80])

print("\nSPLIT", "PASSED" if not fail else f"FAILED: {fail}")
sys.exit(1 if fail else 0)
