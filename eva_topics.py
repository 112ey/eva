"""Ева (fork): темы (ветки) в форум-группах — читать названия и понимать, куда написать.

У Telegram нет метода «дай список тем», поэтому названия собираются из самих апдейтов: каждое
сообщение в ветке приносит `message_thread_id`, а имя темы лежит в `reply_to_message.forum_topic_created.name`
(и в сервисном сообщении создания темы). Адаптер отдаёт это сюда, а здесь хранится файл
`<home>/topics.json` вида `{chat_id: {thread_id: {"name": ..., "last_seen": ...}}}`.

Дальше три вещи:
* ``prompt_block`` — список тем для её промта: она видит, как называются ветки;
* ``parse_marker`` — маркер ``[[тема: Мемы]]`` в начале сообщения, по которому её текст уходит
  в нужную ветку (адаптер снимает маркер и подменяет thread_id при отправке);
* ``best_thread`` — выбор темы по смыслу текста, для её собственных сообщений (таймер сам решает,
  в какую ветку писать, а не валит всё в General).
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Optional

HOME = Path(os.environ.get("HERMES_HOME") or (Path.home() / "eva-home"))
TOPICS_FILE = HOME / "topics.json"

_MARKER = re.compile(r"^\s*\[\[\s*тема\s*:\s*(?P<name>[^\]\|]{1,64}?)\s*\]\]\s*", re.IGNORECASE)
_GENERAL = {"general", "общее", "общий"}


def _load() -> dict:
    try:
        data = json.loads(TOPICS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(data: dict) -> None:
    try:
        TOPICS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = TOPICS_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(TOPICS_FILE)
    except OSError:
        pass


def record(chat_id, thread_id, name: Optional[str]) -> None:
    """Запомнить тему (вызывается на каждом сообщении из ветки)."""
    chat_id, thread_id = str(chat_id or ""), str(thread_id or "")
    name = (name or "").strip()
    if not chat_id or not thread_id or not name:
        return
    data = _load()
    topics = data.setdefault(chat_id, {})
    entry = topics.setdefault(thread_id, {})
    if entry.get("name") != name:
        entry["name"] = name
    entry["last_seen"] = int(time.time())
    _save(data)


def topics(chat_id) -> dict[str, str]:
    """``{thread_id: name}``, свежие темы первыми."""
    data = _load()
    rows = (data.get(str(chat_id or "")) or {})
    ordered = sorted(rows.items(), key=lambda kv: -int(kv[1].get("last_seen") or 0))
    return {tid: str(item.get("name") or "").strip() for tid, item in ordered if item.get("name")}


def _named(chat_id) -> dict[str, str]:
    """Только темы с внятным названием (General и цифры не в счёт)."""
    return {tid: name for tid, name in topics(chat_id).items()
            if name and name.lower() not in _GENERAL and not name.isdigit()}


def name_of(chat_id, thread_id) -> Optional[str]:
    """Название темы по её id (для строки «Channel Topic» в её промте)."""
    if thread_id is None:
        return None
    return topics(chat_id).get(str(thread_id))


def prompt_block(chat_id, current_thread: Optional[str] = None) -> str:
    """Блок «## Темы» для промта — пустая строка, если тем нет."""
    rows = topics(chat_id)
    if not rows:
        return ""
    lines = []
    for tid, name in rows.items():
        mark = "  ← ты сейчас тут" if current_thread and str(tid) == str(current_thread) else ""
        lines.append(f"- {name} (id {tid}){mark}")
    return (
        "## Темы в этой группе\n"
        "У группы есть ветки (темы), и в каждой свой разговор. Отвечаешь ты обычно там, где тебя "
        "спросили, — это по умолчанию. Но если тебе есть что сказать не по теме этой ветки, "
        "напиши в подходящую: начни сообщение с «[[тема: <название>]]», и оно уйдёт туда "
        "(сам маркер в чат не попадёт). Не тащи разговор в чужую ветку без причины.\n"
        + "\n".join(lines)
    )


def resolve(chat_id, name_or_id) -> Optional[str]:
    """Название темы (точно или по вхождению) либо её id → thread_id."""
    key = str(name_or_id or "").strip()
    if not key:
        return None
    rows = topics(chat_id)
    if key in rows:
        return key
    low = key.lower()
    for tid, name in rows.items():
        if name.lower() == low:
            return tid
    for tid, name in rows.items():
        if low and (low in name.lower() or name.lower() in low):
            return tid
    return None


def parse_marker(text: str) -> tuple[Optional[str], str]:
    """``("Мемы", "текст без маркера")``; если маркера нет — ``(None, исходный текст)``."""
    match = _MARKER.match(text or "")
    if not match:
        return None, text or ""
    return match.group("name").strip(), (text or "")[match.end():]


def best_thread(chat_id, text: str) -> Optional[str]:
    """Тема, лучше всего подходящая под текст (для её собственных сообщений).

    Основа слова сравнивается с основой слов названия, плюс совпадение по первым буквам
    («сериал» ↔ «сериалы», «мем» ↔ «мемы»). «General» и безымянные ветки не предлагаем:
    если ничего не совпало, пусть пишет в текущую.
    """
    named = _named(chat_id)
    if not named:
        return None
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from eva_memory import stems
    except Exception:  # noqa: BLE001
        def stems(value):  # запасной вариант: как есть
            return re.findall(r"[а-яёa-z0-9]{3,}", (value or "").lower())

    def keys(value: str) -> set[str]:
        raw = {w for w in re.findall(r"[а-яёa-z0-9]{3,}", (value or "").lower())}
        try:
            return {w for w in (set(stems(value)) | raw) if len(w) >= 3}
        except Exception:  # noqa: BLE001
            return raw

    text_keys = keys(text)
    if not text_keys:
        return None
    best: tuple[int, Optional[str]] = (0, None)
    for tid, name in named.items():
        name_keys = keys(name)
        overlap = sum(1 for key in name_keys if any(key[:3] == t[:3] for t in text_keys))
        if overlap > best[0]:
            best = (overlap, tid)
    return best[1] if best[0] > 0 else None


def describe(chat_id) -> str:
    """Человекочитаемая сводка (для логов и проверок)."""
    rows = topics(chat_id)
    if not rows:
        return "тем не знаю"
    return ", ".join(f"{name} (id {tid})" for tid, name in rows.items())
