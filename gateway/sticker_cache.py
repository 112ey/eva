"""Sticker description cache for Telegram.

Stickers are described via the vision tool once and cached by file_unique_id
(``~/.hermes/sticker_cache.json``) so the same image is never re-analyzed.
"""

import asyncio
import json
import threading
import time
from pathlib import Path
from typing import Optional

from hermes_cli.config import get_hermes_home
from utils import atomic_json_write

CACHE_PATH = get_hermes_home() / "sticker_cache.json"
_CACHE_PATH_AT_IMPORT = CACHE_PATH


def _resolve_cache_path() -> Path:
    """Active profile's cache file at call time: the patched ``CACHE_PATH`` when a test changed
    it, else live profile-scoped HERMES_HOME — under the multiplexed gateway one process serves
    every profile, so the import-time constant would pin every profile to the launch home."""
    return CACHE_PATH if CACHE_PATH != _CACHE_PATH_AT_IMPORT else get_hermes_home() / "sticker_cache.json"

# Kept concise to save tokens.
STICKER_VISION_PROMPT = (
    # Eva (fork): короткая подпись по-русски. Описание читают двое — персона (в окне чата) и фильтр,
    # который выбирает стикер по смыслу; длинные английские фразы «The image depicts…» им только мешают
    # и занимают по 80 символов на строку в промте.
    "Опиши стикер коротко и по-русски: что на картинке и что он выражает, 3-8 слов. "
    "Без вводных фраз вроде «на картинке изображено», без переводов текста с картинки, "
    "без точки в конце. Пример: «кот закатывает глаза, скучающий вид»."
)


def _load_cache() -> dict:
    """Load the sticker cache from disk (utf-8-sig: BOM-tolerant read fix)."""
    path = _resolve_cache_path()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):  # OSError covers FileNotFoundError
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    atomic_json_write(_resolve_cache_path(), cache)


# Serializes the read-modify-write in ``cache_sticker_description``. Nothing
# re-acquires it while held (the async wrapper only dispatches the sync form
# to a worker thread), so a plain Lock suffices.
_CACHE_LOCK = threading.Lock()


def get_cached_description(file_unique_id: str) -> Optional[dict]:
    """Return ``{description, emoji, set_name, cached_at}`` or None."""
    return _load_cache().get(file_unique_id)


def cache_sticker_description(
    file_unique_id: str, description: str, emoji: str = "", set_name: str = "", file_id: str = ""
) -> None:
    """Store a vision-generated description under Telegram's stable sticker id.

    ``file_id`` (Eva fork) — не для описания, а чтобы персона могла отправить этот стикер обратно
    (``sendSticker`` принимает только file_id, и он валиден лишь для того бота, который его получил).

    Blocking: ``atomic_json_write`` ends in ``os.replace``. Callers on the event
    loop must use :func:`cache_sticker_description_async`.
    """
    entry = {"description": description, "emoji": emoji, "set_name": set_name,
             "cached_at": time.time()}
    if file_id:
        entry["file_id"] = file_id
    # The lock makes the load/mutate/save triple atomic across worker threads.
    with _CACHE_LOCK:
        _save_cache({**_load_cache(), file_unique_id: entry})


async def cache_sticker_description_async(
    file_unique_id: str, description: str, emoji: str = "", set_name: str = "", file_id: str = ""
) -> None:
    """Off-loop form of :func:`cache_sticker_description`.

    The write ends in ``os.replace``, whose duration is unbounded under
    filesystem pressure, and the only caller is Telegram's ``_handle_sticker``
    -- an inbound-message coroutine. Paying the rename inline stalls every
    adapter and every in-flight turn in the process for its duration.
    """
    await asyncio.to_thread(
        cache_sticker_description, file_unique_id, description, emoji, set_name, file_id
    )


# --- Eva (fork): библиотека стикеров, которые персона может отправить сама ---------------

def known_stickers(limit: int = 40) -> list[dict]:
    """Стикеры, которые она видела (с file_id), свежие первыми."""
    items = [entry for entry in _load_cache().values() if entry.get("file_id")]
    items.sort(key=lambda entry: -float(entry.get("cached_at") or 0))
    return items[:limit]


def find_sticker(query: str) -> Optional[dict]:
    """Стикер по эмодзи, по слову из описания или «любой» (случайный из библиотеки).

    Ищет по ВСЕЙ библиотеке с file_id, а не по ``known_stickers``: та отдаёт только 40 самых
    свежих, и персона не находила бы стикеры, увиденные больше пары часов назад (на практике
    2/3 её «[[стикер: 😏]]» молча проваливались именно поэтому).
    """
    import random

    query = (query or "").strip().lower()
    items = known_stickers(limit=len(_load_cache()))
    if not items:
        return None
    if not query or query in {"любой", "random", "какой-нибудь", "*"}:
        return random.choice(items)
    for entry in items:
        if query == str(entry.get("emoji") or "").strip().lower():
            return entry
    for entry in items:
        if query in str(entry.get("emoji") or "").lower():
            return entry
    words = [word for word in query.split() if len(word) > 2]
    best: tuple[int, Optional[dict]] = (0, None)
    for entry in items:
        haystack = f"{entry.get('description', '')} {entry.get('emoji', '')}".lower()
        score = sum(1 for word in words if word[:5] in haystack)
        if score > best[0]:
            best = (score, entry)
    return best[1] if best[0] else None


def sticker_hint(limit: int = 10, width: int = 46) -> str:
    """Компактный список «что у неё есть» для промта."""
    lines = []
    for entry in known_stickers(limit):
        text = " ".join(str(entry.get("description") or "").split())[:width]
        emoji = entry.get("emoji") or ""
        lines.append(f"- {emoji} {text}".strip())
    return "\n".join(lines)


def build_sticker_injection(description: str, emoji: str = "", set_name: str = "") -> str:
    """Warm-style injection text, e.g.
    ``[The user sent a sticker 😀 from "MyPack"~ It shows: "A cat waving" (=^.w.^=)]``.
    ``set_name`` is only shown together with an emoji."""
    context = f" {emoji}" if emoji else ""
    if set_name and emoji:
        context += f' from "{set_name}"'
    return f'[The user sent a sticker{context}~ It shows: "{description}" (=^.w.^=)]'


def build_animated_sticker_injection(emoji: str = "") -> str:
    """Injection text for animated/video stickers we can't analyze."""
    if emoji:
        return (f"[The user sent an animated sticker {emoji}~ "
                f"I can't see animated ones yet, but the emoji suggests: {emoji}]")
    return "[The user sent an animated sticker~ I can't see animated ones yet]"
