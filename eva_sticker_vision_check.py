"""Проверка: анимированный/видео-стикер можно посмотреть — по статичному превью (thumbnail)."""
import asyncio, json, os, re, sys, urllib.parse, urllib.request
from pathlib import Path
sys.path.insert(0, "/home/iizey/eva-hermes")
os.environ.setdefault("HERMES_HOME", "/home/iizey/eva-home")

tok = re.search(r'^TELEGRAM_BOT_TOKEN=(.*)$', open(os.path.expanduser("~/eva-home/.env")).read(), re.M).group(1).strip()
B = f"http://127.0.0.1:8081/bot{tok}"


def api(method, **params):
    with urllib.request.urlopen(B + f"/{method}?" + urllib.parse.urlencode(params), timeout=30) as r:
        return json.loads(r.read())


fail = []
sticker = api("getStickerSet", name="HotCherry")["result"]["stickers"][0]
thumb = sticker.get("thumbnail")
ok = True
if (sticker.get("is_animated") or sticker.get("is_video")) and thumb:
    from telegram import Bot
    bot = Bot(token=tok, base_url="http://127.0.0.1:8081/bot")

    async def fetch():
        file_obj = await bot.get_file(thumb["file_id"])
        return bytes(await file_obj.download_as_bytearray())

    raw = asyncio.run(fetch())
    path = "/home/iizey/.hermes/cache/scratch/eva-animated-preview.webp"
    Path(path).write_bytes(raw)
    print(f"[ok] превью анимированного стикера скачано: {len(raw)} байт → {path}")
    from tools.vision_tools import vision_analyze_tool
    from gateway.sticker_cache import STICKER_VISION_PROMPT
    result = json.loads(asyncio.run(vision_analyze_tool(image_url=path, user_prompt=STICKER_VISION_PROMPT)))
    description = str(result.get("analysis") or "")
    ok = bool(result.get("success")) and len(description) > 10
    print(f"[{'ok' if ok else 'FAIL'}] зрение описало превью: {description[:180]}")
else:
    print("[FAIL] у анимированного стикера нет thumbnail")
    ok = False
print("STICKER-VISION", "PASSED" if ok else "FAILED")
sys.exit(0 if ok else 1)
