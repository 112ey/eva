"""Скачивание файла стикера (анимированного превью) — каким путём оно вообще работает."""
import asyncio, json, os, re, sys, urllib.parse, urllib.request
from pathlib import Path
sys.path.insert(0, "/home/iizey/eva-hermes")
os.environ.setdefault("HERMES_HOME", "/home/iizey/eva-home")

tok = re.search(r'^TELEGRAM_BOT_TOKEN=(.*)$', open(os.path.expanduser("~/eva-home/.env")).read(), re.M).group(1).strip()
B = f"http://127.0.0.1:8081/bot{tok}"


def api(method, **params):
    with urllib.request.urlopen(B + f"/{method}?" + urllib.parse.urlencode(params), timeout=30) as r:
        return json.loads(r.read())


sticker = api("getStickerSet", name="HotCherry")["result"]["stickers"][0]
thumb_id = sticker["thumbnail"]["file_id"]
info = api("getFile", file_id=thumb_id)["result"]
path = info.get("file_path") or ""
print("file_path из API:", path[:90])

# 1) локальный путь прямо с диска
local_ok = False
try:
    data = Path(path).read_bytes()
    print(f"[ok] файл прочитан с диска: {len(data)} байт")
    local_ok = len(data) > 0
except Exception as exc:
    print("[FAIL] с диска не прочитать:", str(exc)[:80])

# 2) тот же путь, которым пользуется адаптер (python-telegram-bot + локальный Bot API)
async def ptb_download():
    from telegram import Bot
    bot = Bot(token=tok, base_url=f"http://127.0.0.1:8081/bot")
    file_obj = await bot.get_file(thumb_id)
    raw = await file_obj.download_as_bytearray()
    return bytes(raw)

try:
    raw = asyncio.run(ptb_download())
    print(f"[ok] python-telegram-bot скачал: {len(raw)} байт")
    ptb_ok = len(raw) > 0
except Exception as exc:
    print("[FAIL] python-telegram-bot не скачал:", type(exc).__name__, str(exc)[:120])
    ptb_ok = False

print("STICKER-DOWNLOAD", "PASSED" if (local_ok or ptb_ok) else "FAILED", f"(диск={local_ok}, ptb={ptb_ok})")
sys.exit(0 if (local_ok or ptb_ok) else 1)
