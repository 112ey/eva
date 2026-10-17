"""Проверка ответа стикером из пака: вердикт «СТИКЕР <номер>» → отправка нужного стикера."""
import asyncio
import json
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, "/home/iizey/eva-hermes")

import eva_sticker_pack as pack_mod  # noqa: E402
import plugins.platforms.telegram.adapter as adapter_mod  # noqa: E402
from plugins.platforms.telegram.adapter import TelegramAdapter  # noqa: E402
from plugins.platforms.telegram.eva_gate import _parse_classify  # noqa: E402

fail = []


def check(name, cond, extra=""):
    print(f"[{'ok' if cond else 'FAIL'}] {name}{' — ' + str(extra) if extra else ''}")
    if not cond:
        fail.append(name)


# 1. Разбор вердикта
for text, want in [
    ("СТИКЕР 3", ("sticker", "3")),
    ("стикер 12", ("sticker", "12")),
    ("Стикер №7", ("sticker", "7")),
    ("ДА", ("reply", "")),
    ("РЕАКЦИЯ 🔥", ("react", "🔥")),
    ("НЕТ", ("silent", "")),
    ("СТИКЕР", ("silent", "")),          # номер не назван — лучше молчать
]:
    got = _parse_classify(text)
    check(f"разбор {text!r}", got == want, got)

# 2. Пак: список для фильтра и выбор по номеру
tmp = Path(tempfile.mkdtemp())
pack_mod.PACK_FILE = tmp / "sticker_pack.json"
pack_mod.LIBRARY_FILE = tmp / "sticker_cache.json"
pack_mod.PACK_FILE.write_text(json.dumps({
    "name": "k0shbss", "title": "k0shbss",
    "stickers": [
        {"file_id": "F1", "file_unique_id": "u1", "emoji": "🤣", "description": "ржёт во весь рот"},
        {"file_id": "F2", "file_unique_id": "u2", "emoji": "😡", "description": "злится и посылает"},
        {"file_id": "F3", "file_unique_id": "u3", "emoji": "🥰", "description": "мило умиляется"},
    ]}, ensure_ascii=False), encoding="utf-8")

listing = pack_mod.pack_for_prompt()
check("список для фильтра пронумерован", listing.startswith("1) 🤣") and "3) 🥰" in listing, listing.replace("\n", " | "))
check("номер 2 — правильный стикер", (pack_mod.sticker_by_number("2") or {}).get("file_id") == "F2")
check("номер вне списка — ничего", pack_mod.sticker_by_number("99") == {})
check("мусор вместо номера — ничего", pack_mod.sticker_by_number("абракадабра") == {})


class Bot:
    def __init__(self):
        self.calls = []

    def send_sticker(self, **kwargs):
        self.calls.append(kwargs)
        return _coro()


async def _coro():
    return types.SimpleNamespace(message_id=555)


class _Stub(TelegramAdapter):
    name = "Telegram"


stub = object.__new__(_Stub)
stub._bot = Bot()
stub.config = types.SimpleNamespace(extra={"eva_pack_sticker_cooldown_seconds": 0})
stub._eva_pack_at = {}
stub._eva_recent = {}
stub._is_group_chat = lambda message: True
stub._eva_note_own_message = lambda chat_id, content: None
stub._eva_remember_group_line = lambda msg: None

message = types.SimpleNamespace(chat=types.SimpleNamespace(id=-1002222222222), message_id=42,
                               message_thread_id=9245,
                               from_user=types.SimpleNamespace(id=1, full_name="Роман"), text="ахахах")


async def _send(number="2"):
    ok = TelegramAdapter._eva_send_pack_sticker(stub, message, number)
    await asyncio.sleep(0.05)
    return ok


check("стикер уходит в Bot API", asyncio.run(_send("2")) is True)
call = stub._bot.calls[-1] if stub._bot.calls else {}
check("file_id правильный", call.get("sticker") == "F2", call)
check("чат правильный", str(call.get("chat_id")).endswith("1002222222222"), call)
check("ветка (тема) передаётся", call.get("message_thread_id") == 9245, call)

# 3. Пауза: второй стикер подряд не уходит
stub.config.extra["eva_pack_sticker_cooldown_seconds"] = 120
stub._eva_pack_at = {}
stub._bot.calls.clear()
asyncio.run(_send("1"))
second = asyncio.run(_send("3"))
check("первый стикер ушёл", len(stub._bot.calls) == 1, len(stub._bot.calls))
check("второй подряд — нет (пауза)", second is False and len(stub._bot.calls) == 1, second)

# 4. Вердикт фильтра «стикер» не открывает ход, а отправляет картинку
stub.config.extra["eva_pack_sticker_cooldown_seconds"] = 0
stub._eva_pack_at = {}
stub._bot.calls.clear()
observed = []
stub._eva_gate_classify = lambda msg, merged=None: ("sticker", "3")
stub._should_process_message = lambda msg: False
stub._should_observe_unmentioned_group_message = lambda msg: True
stub._observe_unmentioned_group_message = lambda msg, msg_type, update_id=None: observed.append(msg.text)


async def _run_gate():
    result = TelegramAdapter._gate_or_observe(stub, message, types.SimpleNamespace(update_id=1), "text")
    await asyncio.sleep(0.05)
    return result


proceed = asyncio.run(_run_gate())
check("вердикт «стикер» не открывает ход", proceed is False, proceed)
check("при этом стикер отправлен", stub._bot.calls and stub._bot.calls[-1]["sticker"] == "F3",
      stub._bot.calls[-1] if stub._bot.calls else None)
check("сообщение попало в наблюдение", observed == ["ахахах"], observed)

# 5. Без пака вердикт игнорируется (пустой список — фильтр его и не получит)
pack_mod.PACK_FILE = tmp / "missing.json"
check("без пака список пустой", pack_mod.pack_for_prompt() == "")
check("без пака стикер не уйдёт", asyncio.run(_send("1")) is False)

print("\nPACK-STICKER", "PASSED" if not fail else f"FAILED: {fail}")
sys.exit(1 if fail else 0)
