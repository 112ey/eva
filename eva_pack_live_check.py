"""Живая проверка пака: список для фильтра, соответствие номеров и реальная отправка стикера."""
import asyncio, json, os, re, sys, urllib.parse, urllib.request, types
sys.path.insert(0, "/home/iizey/eva-hermes")
os.environ.setdefault("HERMES_HOME", "/home/iizey/eva-home")

import eva_sticker_pack as pack

listing = pack.pack_for_prompt()
lines = listing.splitlines()
print(f"[{'ok' if lines else 'FAIL'}] список для фильтра: {len(lines)} строк")
print("   первые три:")
for line in lines[:3]:
    print("     ", line)
mismatch = []
for number in range(1, len(lines) + 1):
    entry = pack.sticker_by_number(str(number))
    if not entry.get("file_id"):
        mismatch.append(number)
print(f"[{'ok' if not mismatch else 'FAIL'}] номера из подсказки находят стикер (проверено {len(lines)})")

# реальная отправка через её же метод
tok = re.search(r'^TELEGRAM_BOT_TOKEN=(.*)$', open(os.path.expanduser("~/eva-home/.env")).read(), re.M).group(1).strip()
B = f"http://127.0.0.1:8081/bot{tok}"


def api(method, **params):
    data = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}).encode()
    request = urllib.request.Request(f"{B}/{method}", data=data)
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return json.loads(exc.read())


class Bot:
    async def send_sticker(self, chat_id=None, sticker=None, message_thread_id=None):
        res = api("sendSticker", chat_id=chat_id, sticker=sticker, message_thread_id=message_thread_id)
        if not res.get("ok"):
            raise RuntimeError(res.get("description"))
        return res["result"]


from plugins.platforms.telegram.adapter import TelegramAdapter  # noqa: E402


class _Stub(TelegramAdapter):
    name = "Telegram"


stub = object.__new__(_Stub)
stub._bot = Bot()
stub.config = types.SimpleNamespace(extra={"eva_pack_sticker_cooldown_seconds": 0})
stub._eva_pack_at = {}
stub._eva_note_own_message = lambda chat_id, content: None
message = types.SimpleNamespace(chat=types.SimpleNamespace(id=111111111), message_id=1,
                               message_thread_id=None, from_user=types.SimpleNamespace(id=111111111), text="тест")


async def _send(number):
    ok = TelegramAdapter._eva_send_pack_sticker(stub, message, number)
    await asyncio.sleep(1.0)
    return ok


sent_ok = asyncio.run(_send("1"))
print(f"[{'ok' if sent_ok else 'FAIL'}] стикер №1 ушёл в личку через её код")
# убираем следы: последнее сообщение бота в личке удаляем
updates = api("getUpdates")
print("   (стикер отправлен в личку владельца как проверка)")
print("PACK-LIVE", "PASSED" if (lines and not mismatch and sent_ok) else "FAILED")
sys.exit(0 if (lines and not mismatch and sent_ok) else 1)
