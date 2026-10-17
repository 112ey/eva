"""Проверка стикеров: библиотека с file_id, маркер «[[стикер: …]]», отправка без текста."""
import asyncio
import json
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, "/home/iizey/eva-hermes")
sys.path.insert(0, "/home/iizey/eva-home")

import gateway.sticker_cache as sc  # noqa: E402
from plugins.platforms.telegram.adapter import TelegramAdapter  # noqa: E402

fail = []


def check(name, cond, extra=""):
    print(f"[{'ok' if cond else 'FAIL'}] {name}{' — ' + str(extra) if extra else ''}")
    if not cond:
        fail.append(name)


tmp = Path(tempfile.mkdtemp()) / "sticker_cache.json"
sc.CACHE_PATH = tmp

# 1. Библиотека: file_id сохраняется и находится по эмодзи/слову
sc.cache_sticker_description("uniq-cat", "кот машет лапой и смеётся", "😺", "MyCats", file_id="FILE-CAT")
sc.cache_sticker_description("uniq-sad", "грустный пёс под дождём", "😢", "Dogs", file_id="FILE-DOG")
sc.cache_sticker_description("uniq-noid", "без file_id — отправить нельзя", "😐", "X")
library = sc.known_stickers()
check("в библиотеке только стикеры с file_id", [e["file_id"] for e in library] == ["FILE-DOG", "FILE-CAT"],
      [e["file_id"] for e in library])
check("поиск по эмодзи", (sc.find_sticker("😺") or {}).get("file_id") == "FILE-CAT")
check("поиск по слову из описания", (sc.find_sticker("пёс дождь") or {}).get("file_id") == "FILE-DOG")
check("«любой» отдаёт что-то из библиотеки", (sc.find_sticker("любой") or {}).get("file_id") in {"FILE-CAT", "FILE-DOG"})
check("несуществующий стикер не находится", sc.find_sticker("космонавт") is None)
check("подсказка для промта перечисляет эмодзи", "😺" in sc.sticker_hint() and "😢" in sc.sticker_hint(),
      sc.sticker_hint().replace("\n", " | "))

# 2. Маркер в тексте
class _Stub(TelegramAdapter):
    name = "Telegram"


stub = object.__new__(_Stub)
clean, file_id = TelegramAdapter._eva_resolve_sticker_marker(stub, "[[стикер: 😺]]")
check("только маркер → пустой текст + file_id", (clean, file_id) == ("", "FILE-CAT"), (clean, file_id))
clean, file_id = TelegramAdapter._eva_resolve_sticker_marker(stub, "[[стикер: грустный пёс]] ну держись")
check("маркер со словом + текст", (clean, file_id) == ("ну держись", "FILE-DOG"), (clean, file_id))
clean, file_id = TelegramAdapter._eva_resolve_sticker_marker(stub, "[[стикер: космонавт]] привет")
check("неизвестный ключ → маркер убран, текста не теряем", (clean, file_id) == ("привет", None), (clean, file_id))
clean, file_id = TelegramAdapter._eva_resolve_sticker_marker(stub, "просто текст")
check("без маркера ничего не меняется", (clean, file_id) == ("просто текст", None), (clean, file_id))


# 3. Отправка стикера: реальные параметры вызова Bot API
class FakeBot:
    def __init__(self):
        self.calls = []

    async def send_sticker(self, **kwargs):
        self.calls.append(kwargs)
        return types.SimpleNamespace(message_id=555)


stub._bot = FakeBot()
stub._eva_recent = {}
stub._eva_seeded = set()
stub._is_group_chat = lambda message: False
result = asyncio.run(TelegramAdapter._eva_send_sticker(stub, "-1001111111111", "FILE-CAT", {"thread_id": "9245"}))
call = stub._bot.calls[0]
check("стикер ушёл в Bot API с нужным file_id", call.get("sticker") == "FILE-CAT", call)
check("стикер ушёл в нужный чат", str(call.get("chat_id")).endswith("1001111111111"), call)
check("тема (thread) передаётся", call.get("message_thread_id") == 9245, call)
check("результат успешный, с id сообщения", result.success and result.message_id == "555", result)

# 4. send(): сообщение-стикер не уходит текстом
sent_messages = []
stub._eva_send_sticker = lambda chat_id, file_id, metadata=None: _fake_sticker(chat_id, file_id, sent_messages)

async def _fake_sticker(chat_id, file_id, out):
    out.append(("sticker", file_id))
    return types.SimpleNamespace(success=True, message_id="1")


def _no_text(*args, **kwargs):
    raise AssertionError("текст не должен отправляться, если сообщение состоит из стикера")


stub._send_text_locked = _no_text
stub._chat_send_lock = lambda chat_id: _null_lock()
stub._eva_apply_topic_marker = lambda chat_id, content, metadata: (content, metadata)
stub._eva_note_own_message = lambda chat_id, content: None
stub._eva_muted = lambda: False   # рубильник владельца в тесте не участвует
asyncio.run(TelegramAdapter.send(stub, "-1001111111111", "[[стикер: 😺]]"))
check("send() отправил только стикер", sent_messages == [("sticker", "FILE-CAT")], sent_messages)


class _null_lock:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc):
        return False


# 5. Таймер (send_local) понимает тот же маркер
import send_local  # noqa: E402

text, file_id = send_local.split_sticker_marker("[[стикер: 😢]]")
check("send_local: маркер → file_id", (text, file_id) == ("", "FILE-DOG"), (text, file_id))
text, file_id = send_local.split_sticker_marker("[[стикер: 😢]] и текст")
check("send_local: маркер + текст", (text, file_id) == ("и текст", "FILE-DOG"), (text, file_id))

# 6. Блок для промта: она видит, что у неё есть и как этим пользоваться
block = TelegramAdapter._eva_stickers_prompt(stub)
check("в промт попадает объяснение маркера", "[[стикер:" in block and "Твои стикеры" in block, block[:80])
check("в промте есть её стикеры", "😺" in block and "😢" in block)

print("\nSTICKERS", "PASSED" if not fail else f"FAILED: {fail}")
sys.exit(1 if fail else 0)
