"""Проверка: служебный маркер молчания не доезжает до чата.

Живой случай из «Финтифлюшкеров»: модель написала «[SILENT]» первой строкой, а под ней настоящий
ответ — и маркер ушёл в группу вместе с ним.
"""
import asyncio
import sys
import types

sys.path.insert(0, "/home/iizey/eva-hermes")

from gateway.platforms.base import SendResult  # noqa: E402
from plugins.platforms.telegram.adapter import TelegramAdapter  # noqa: E402

fail = []


def check(name, cond, extra=""):
    print(f"[{'ok' if cond else 'FAIL'}] {name}{' — ' + str(extra) if extra else ''}")
    if not cond:
        fail.append(name)


class _Stub(TelegramAdapter):
    name = "Telegram"


stub = object.__new__(_Stub)

# 1. Сам разбор маркера
cases = [
    ("живой случай из группы", "[SILENT]\nребёнок? мне вообще-то пятнадцать, если что (￣ヘ￣)",
     ("ребёнок? мне вообще-то пятнадцать, если что (￣ヘ￣)", False)),
    ("маркер и текст в одну строку", "[SILENT] нет, не пойду", ("нет, не пойду", False)),
    ("только маркер", "[SILENT]", ("", True)),
    ("маркер без скобок", "SILENT", ("", True)),
    ("NO_REPLY", "NO_REPLY", ("", True)),
    ("китайский маркер", "【静默】", ("", True)),
    ("маркер с точкой", "NO REPLY.", ("", True)),
    ("нижний регистр", "[silent]\nок, молчу", ("ок, молчу", False)),
    ("маркер в середине строки не трогаем", "я смотрела silent hill", ("я смотрела silent hill", False)),
    ("упоминание в тексте не трогаем", "он сказал no reply и ушёл", ("он сказал no reply и ушёл", False)),
    ("обычный ответ не тронут", "мне вообще-то пятнадцать (￣ヘ￣)", ("мне вообще-то пятнадцать (￣ヘ￣)", False)),
    ("маркер в конце строки", "ладно\n[SILENT]", ("ладно", False)),
    ("несколько маркеров", "[SILENT]\nтекст\nNO_REPLY", ("текст", False)),
    ("пустой ответ", "", ("", False)),
]
for label, raw, want in cases:
    got = TelegramAdapter._eva_strip_silence_marker(stub, raw)
    check(f"разбор: {label}", got == want, f"{got!r} (ждали {want!r})")

# 2. Путь отправки: что реально уходит в Telegram
sent: list = []


async def _fake_locked(chat_id, content, reply_to, metadata):
    sent.append(content)
    return SendResult(success=True, message_id=1)


stub._send_text_locked = _fake_locked
# Рубильник владельца читается живьём: при включённом /fuckingstop отправка отменяется до всех
# маркеров, и тест падал бы «не по делу». Проверяем сам разбор — глушим проверку тишины.
import json as _json  # noqa: E402
import os as _os  # noqa: E402
_ctl = _os.path.expanduser("~/eva-home/control.json")
try:
    _muted = bool(_json.load(open(_ctl, encoding="utf-8")).get("muted"))
except Exception:  # noqa: BLE001
    _muted = False
print(f"[info] рубильник владельца: {'заткнута' if _muted else 'говорит'} (тест работает независимо)")
stub._eva_muted = lambda: False
stub._eva_note_own_message = lambda chat_id, content: None
stub._bot = types.SimpleNamespace()


async def run(text):
    sent.clear()
    return await TelegramAdapter.send(stub, "222222222", text)


result = asyncio.run(run("[SILENT]\nребёнок? мне вообще-то пятнадцать, если что (￣ヘ￣)"))
check("в чат ушёл только ответ, без маркера", sent == ["ребёнок? мне вообще-то пятнадцать, если что (￣ヘ￣)"], sent)
check("отправка при этом успешная", bool(getattr(result, "success", False)), result)

result = asyncio.run(run("[SILENT]"))
check("один маркер — в Telegram не уходит ничего", sent == [], sent)
check("и это не считается ошибкой", bool(getattr(result, "success", False)), result)

result = asyncio.run(run("ок, я тут"))
check("обычный ответ уходит как есть", sent == ["ок, я тут"], sent)

# 3. Тот же маркер на таймерном пути (мимо адаптера, через send_local)
sys.path.insert(0, "/home/iizey/eva-home")
import send_local  # noqa: E402

for label, raw, want in [("таймер: маркер и ответ", "[SILENT]\nладно, я тут", "ладно, я тут"),
                         ("таймер: только маркер", "[SILENT]", ""),
                         ("таймер: обычный текст", "просто текст", "просто текст")]:
    got = send_local.strip_silence_marker(raw)
    check(label, got == want, f"{got!r} (ждали {want!r})")

print("\nSILENCE-MARKER", "PASSED" if not fail else f"FAILED: {fail}")
sys.exit(1 if fail else 0)
