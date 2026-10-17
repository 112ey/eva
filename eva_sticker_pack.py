"""Ева (fork): наборы стикеров, которыми она отвечает вместо слов.

Зачем: «если ответ однозначный — ответь стикером». Чтобы фильтр мог выбрать стикер, ему нужен
нумерованный список с человеческим описанием каждого, а адаптеру — ``file_id`` (только по нему
Telegram разрешает отправку, и он валиден лишь для её бота).

Что делает скрипт:

    python3 eva_sticker_pack.py --name <имя_набора> [--limit 100] [--apply]

1. тянет набор через ``getStickerSet`` (имя — это часть ссылки ``t.me/addstickers/<имя>``);
2. качает каждый стикер (у анимированных и видео берёт статичное превью) и описывает его её зрением;
3. дописывает набор в ``~/eva-home/sticker_pack.json`` — наборов может быть много, а номера для
   фильтра считаются по всем вместе;
4. складывает те же стикеры в общую библиотеку, чтобы она могла звать их и вручную
   («[[стикер: 😂]]»).

Описания кэшируются по ``file_unique_id``: повторный запуск докачивает только новое. Файл
сохраняется по ходу — прогон на сотню стикеров идёт минутами, терять его нельзя.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

HOME = Path(os.environ.get("HERMES_HOME") or (Path.home() / "eva-home"))
PACK_FILE = HOME / "sticker_pack.json"
LIBRARY_FILE = HOME / "sticker_cache.json"
LOG = HOME / "logs" / "sticker_pack.log"
PROMPT_LIMIT = 40          # больше сорока строк фильтру не нужно: он всё равно берёт одну
log = logging.getLogger("eva.sticker_pack")


def _token() -> str:
    for candidate in (HOME / ".env", Path.home() / ".hermes" / ".env"):
        try:
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        match = re.search(r"^TELEGRAM_BOT_TOKEN\s*=\s*(.+)$", text, re.M)
        if match:
            return match.group(1).strip().strip('"').strip("'")
    return ""


def _api(method: str, **params):
    import urllib.error
    import urllib.parse
    import urllib.request
    base = os.environ.get("EVATM_LOCAL_API", "http://127.0.0.1:8081")
    data = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}).encode()
    request = urllib.request.Request(f"{base}/bot{_token()}/{method}", data=data)
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:  # noqa: BLE001
        return json.loads(exc.read())


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _library() -> dict:
    return _load(LIBRARY_FILE, {})


def load_packs() -> dict:
    """Все наборы: ``{имя: {title, updated_at, stickers: [...]}}``.

    Понимает и старый формат (один набор списком в корне файла) — он оборачивается в словарь, так что
    уже собранные описания не теряются.
    """
    data = _load(PACK_FILE, {})
    if not isinstance(data, dict):
        return {}
    packs = data.get("packs")
    if isinstance(packs, dict) and packs:
        return packs
    if data.get("stickers"):
        return {data.get("name") or "pack": data}
    return {}


def _save_packs(packs: dict) -> None:
    # Атомарно: пока идёт сборка набора (файл переписывается на каждом стикере), гейтвей читает его
    # же — половина JSON означала бы «списка нет» и она молча теряла бы стикеры на всё время сборки.
    tmp = PACK_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(
        {"packs": packs, "updated_at": int(time.time())}, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, PACK_FILE)


def _save_library(library: dict) -> None:
    tmp = LIBRARY_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(library, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, LIBRARY_FILE)


def _entries() -> list:
    """Все стикеры всех наборов; у каждого помечен свой набор."""
    out = []
    for name, pack in load_packs().items():
        for entry in pack.get("stickers") or []:
            item = dict(entry)
            item["pack"] = name
            out.append(item)
    return out


def _pick_order(stickers: list, limit: int = PROMPT_LIMIT) -> list:
    """Порядок показа фильтру: по одному стикеру на эмоцию, по кругу между наборами.

    Наборы большие, и подряд идут вариации одного и того же — фильтру нужен выбор по смыслу, а не
    сорок похожих котов. Поэтому идём «по кругу»: в каждом раунде берём по одному ещё не показанному
    стикеру из КАЖДОГО набора (иначе один большой набор займёт весь список, а второй не будет виден
    вообще), и внутри набора пропускаем уже показанные эмоции.
    """
    by_pack: dict[str, list[int]] = {}
    for index, entry in enumerate(stickers):
        by_pack.setdefault(str(entry.get("pack") or ""), []).append(index)

    picked: list[int] = []
    seen_emoji: set[str] = set()
    cursors = {name: 0 for name in by_pack}
    while len(picked) < limit:
        progressed = False
        for name, items in by_pack.items():
            while cursors[name] < len(items):
                index = items[cursors[name]]
                cursors[name] += 1
                emoji = (stickers[index].get("emoji") or "").strip()
                if emoji and emoji in seen_emoji:
                    continue
                seen_emoji.add(emoji)
                picked.append(index)
                progressed = True
                break
            if len(picked) >= limit:
                break
        if not progressed:
            break
    if len(picked) < limit:
        # Добор идёт В КОНЕЦ списка: если отсортировать, дубликаты эмоций встанут в начало и
        # вытеснят оттуда как раз те стикеры, ради которых первая проходка и делалась.
        rest = [index for index in range(len(stickers)) if index not in set(picked)]
        picked.extend(rest[: max(0, limit - len(picked))])
    return picked


def pack_for_prompt(limit: int = PROMPT_LIMIT) -> str:
    """Нумерованный список стикеров для промта фильтра (пусто, если наборов нет)."""
    stickers = _entries()
    if not stickers:
        return ""
    lines = []
    for number, index in enumerate(_pick_order(stickers, limit), start=1):
        entry = stickers[index]
        description = " ".join(str(entry.get("description") or "").split())[:70]
        emoji = entry.get("emoji") or ""
        lines.append(f"{number}) {emoji} {description}".strip() if description else f"{number}) {emoji} стикер".strip())
    return "\n".join(lines)


def sticker_by_number(number, limit: int = PROMPT_LIMIT) -> dict:
    """Стикер по номеру из вердикта фильтра (нумерация та же, что в подсказке)."""
    stickers = _entries()
    if not stickers:
        return {}
    order = _pick_order(stickers, limit)
    try:
        position = int(str(number).strip())
    except (TypeError, ValueError):
        return {}
    return stickers[order[position - 1]] if 1 <= position <= len(order) else {}


async def _download(sticker: dict) -> tuple[bytes, str]:
    """Картинка для зрения: у видео и анимированных — статичное превью."""
    from telegram import Bot

    bot = Bot(token=_token(), base_url="http://127.0.0.1:8081/bot")
    file_id = sticker["file_id"]
    if sticker.get("is_animated") or sticker.get("is_video"):
        thumbnail = sticker.get("thumbnail")
        if not thumbnail:
            return b"", ""
        file_id = thumbnail["file_id"]
    file_obj = await bot.get_file(file_id)
    raw = bytes(await file_obj.download_as_bytearray())
    return (raw, ".png") if raw[:8] == b"\x89PNG\r\n\x1a\n" else (raw, ".webp")


async def build(name: str, limit: int = 100, apply: bool = False) -> int:
    from gateway.platforms.base import cache_image_from_bytes_async
    from gateway.sticker_cache import STICKER_VISION_PROMPT
    from tools.vision_tools import vision_analyze_tool

    answer = _api("getStickerSet", name=name)
    if not answer.get("ok"):
        print(f"набор {name!r} не найден: {answer.get('description')}")
        return 1
    sticker_set = answer["result"]
    stickers = sticker_set.get("stickers", [])[:limit]
    library = _library()
    packs = load_packs()
    pack = packs.get(name) or {}
    known = {entry.get("file_unique_id"): entry for entry in pack.get("stickers") or []}
    print(f"набор «{sticker_set.get('title')}»: взято {len(stickers)} из {len(sticker_set.get('stickers', []))}"
          f", уже описано в нём {len(known)}; всего наборов {max(len(packs), 1)}")

    def _persist() -> None:
        # Перечитываем файл перед записью: пока набор собирается минутами, в него пишут и другие
        # (например перевод подписей) — со снимком в памяти чужие правки затирались бы.
        fresh = load_packs()
        fresh[name] = {"title": sticker_set.get("title") or name, "updated_at": int(time.time()),
                       "stickers": out}
        packs.clear()
        packs.update(fresh)
        _save_packs(packs)
        _save_library(library)

    out = []
    for index, sticker in enumerate(stickers, start=1):
        uid = sticker["file_unique_id"]
        entry = dict(known.get(uid) or {})
        entry.update({"file_id": sticker["file_id"], "file_unique_id": uid,
                      "emoji": sticker.get("emoji") or entry.get("emoji") or ""})
        cached = bool(known.get(uid, {}).get("description"))
        if not entry.get("description"):
            for attempt in (1, 2):   # зрение иногда отвечает пустым — одна повторная попытка
                try:
                    raw, ext = await _download(sticker)
                    if raw:
                        path = await cache_image_from_bytes_async(raw, ext=ext)
                        result = json.loads(await vision_analyze_tool(image_url=path, user_prompt=STICKER_VISION_PROMPT))
                        entry["description"] = (result.get("analysis") or "").strip() if result.get("success") else ""
                    else:
                        entry["description"] = ""
                except Exception as exc:  # noqa: BLE001
                    log.warning("стикер %s не описала (попытка %d): %s", uid, attempt, exc)
                    entry["description"] = entry.get("description") or ""
                if entry.get("description"):
                    break
        entry["description"] = " ".join(str(entry.get("description") or "").split())[:160]
        out.append(entry)
        print(f"  {index:>3}. {entry['emoji']} {entry['description'][:64]} [{'из кэша' if cached else 'описала'}]")
        library[uid] = {"description": entry["description"] or f"стикер {entry['emoji']}",
                        "emoji": entry["emoji"], "set_name": sticker_set.get("title") or name,
                        "cached_at": time.time(), "file_id": sticker["file_id"], "pack": name}
        if apply:
            # сохраняем по ходу: прогон из десятков стикеров идёт минутами, терять его нельзя
            _persist()

    if apply:
        _persist()
        print(f"\nзаписано: наборов {len(packs)}, стикеров всего {len(_entries())}; "
              f"фильтру показывается {len(_pick_order(_entries(), PROMPT_LIMIT))}")
    else:
        print("\ndry-run: файлы не изменены (нужен --apply)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="имя набора (из t.me/addstickers/<имя>)")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    HOME.joinpath("logs").mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(LOG, encoding="utf-8")])
    sys.path.insert(0, "/home/iizey/eva-hermes")
    return asyncio.run(build(args.name, limit=args.limit, apply=args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
