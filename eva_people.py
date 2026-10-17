"""Ева (fork): кто ей пишет и что она об этих людях знает.

Зачем: у неё не одна общая личка, а разговор с каждым человеком отдельно, и в группе она
разговаривает с теми же людьми. Знание должно быть общим: услышала в группе, что Борис — гитарист,
— в личке с Борисом она это знает.

Хранилище — ``~/eva-home/people.json``: карточка на каждого человека (имя, прозвища, факты,
где виделась). Факты копятся из трёх источников:

* строки чатов (``chat_lines.jsonl``) — их разбирает :mod:`people_sync` через модель;
* её собственная пометка в ответе ``[[запомнить: Борис — играет на гитаре]]`` — работает сразу,
  без лишнего вызова модели;
* наблюдения — имя и «где виделась» обновляются на каждом её входящем сообщении.

Карточка уезжает в промт блоком ``<о_человеке>`` (в личке — про собеседника, в группе — про того,
кто написал), поэтому она воспринимает, с кем говорит.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("eva.people")

HOME = Path(os.environ.get("HERMES_HOME") or (Path.home() / "eva-home"))
STORE = HOME / "people.json"
LINES = HOME / "chat_lines.jsonl"
MAX_FACTS = 40          # больше сорока фактов о человеке в промт не влезет и не нужно
MAX_LINE_BYTES = 4 * 1024 * 1024

MARKER = re.compile(r"\[\[\s*запомнить\s*[:\-]\s*(?P<body>[^\[\]]{3,400})\]\]", re.IGNORECASE)
_DASH = re.compile(r"\s*(?:—|--|–|:)\s*")


def _load() -> dict:
    try:
        data = json.loads(STORE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"people": {}}
    if not isinstance(data, dict):
        return {"people": {}}
    data.setdefault("people", {})
    return data


def _save(data: dict) -> None:
    try:
        STORE.parent.mkdir(parents=True, exist_ok=True)
        STORE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        log.warning("карточки людей не сохранить: %s", exc)


def _key(user_id: Any) -> str:
    return str(user_id or "").strip()


def _normalize(text: str) -> str:
    return " ".join(re.split(r"[^\w]+", str(text or "").lower(), flags=re.UNICODE)).strip()


def note_sighting(user_id: Any, name: str = "", *, chat_id: str = "", chat_title: str = "",
                  when: Optional[float] = None) -> None:
    """Отметить, что человек ей писал (имя и «где виделась»)."""
    key = _key(user_id)
    if not key:
        return
    data = _load()
    person = data["people"].setdefault(key, {"name": "", "aka": [], "facts": [], "chats": [], "seen": 0})
    name = " ".join(str(name or "").split())
    if name and name != person.get("name"):
        aka = [a for a in (person.get("aka") or []) if a]
        if person.get("name") and person["name"] not in aka:
            aka.append(person["name"])
        person["name"] = name
        person["aka"] = aka[-6:]
    chat_id = str(chat_id or "")
    if chat_id and chat_id not in (person.get("chats") or []):
        person.setdefault("chats", []).append(chat_id)
    if chat_title:
        person["chat_title"] = str(chat_title)
    person["seen"] = float(when or time.time())
    _save(data)


def remember(user_id: Any, fact: str, *, source: str = "", name: str = "") -> bool:
    """Записать факт о человеке. Возвращает False, если такой факт уже есть."""
    key = _key(user_id)
    fact = " ".join(str(fact or "").split())
    if not key or len(fact) < 3:
        return False
    data = _load()
    person = data["people"].setdefault(key, {"name": name or "", "aka": [], "facts": [], "chats": [], "seen": 0})
    if name and not person.get("name"):
        person["name"] = name
    normalized = _normalize(fact)
    for entry in person.get("facts") or []:
        existing = _normalize(entry.get("text") or "")
        if existing == normalized or (existing and (existing in normalized or normalized in existing)):
            return False
    person.setdefault("facts", []).append({"text": fact, "source": str(source or "")[:80],
                                           "at": int(time.time())})
    person["facts"] = person["facts"][-MAX_FACTS:]
    person["seen"] = time.time()
    _save(data)
    log.info("о человеке %s запомнила: %s", person.get("name") or key, fact[:80])
    return True


def add_alias(user_id: Any, alias: str) -> None:
    key, alias = _key(user_id), " ".join(str(alias or "").split())
    if not key or not alias:
        return
    data = _load()
    person = data["people"].setdefault(key, {"name": alias, "aka": [], "facts": [], "chats": [], "seen": 0})
    aka = [a for a in (person.get("aka") or []) if a and a != alias]
    if alias != person.get("name"):
        aka.append(alias)
    person["aka"] = aka[-6:]
    _save(data)


def _name_matches(left: str, right: str) -> bool:
    """Похожи ли имена: точное совпадение, вхождение или общая основа («Борис» ↔ «Борька»)."""
    if not left or not right:
        return False
    if left == right or left in right or right in left:
        return True
    prefix = 0
    for a, b in zip(left, right):
        if a != b:
            break
        prefix += 1
    return prefix >= 3 and prefix >= 0.6 * min(len(left), len(right))


def find_by_name(name: str) -> list[str]:
    """id людей, чьё имя/прозвище похоже на названное (для «запомни про Бориса»)."""
    target = _normalize(name)
    if not target:
        return []
    hits = []
    for key, person in (_load().get("people") or {}).items():
        names = [person.get("name") or ""] + list(person.get("aka") or [])
        for candidate in names:
            normalized = _normalize(candidate)
            if _name_matches(normalized, target):
                hits.append(key)
                break
    return hits


def card(user_id: Any, *, limit_facts: int = 12) -> str:
    """Блок «кто это» для промта (пусто, если о человеке ничего не известно)."""
    person = (_load().get("people") or {}).get(_key(user_id)) or {}
    if not person:
        return ""
    name = person.get("name") or ""
    aka = [a for a in (person.get("aka") or []) if a and a != name]
    facts = [f.get("text") for f in (person.get("facts") or []) if f.get("text")]
    if not name and not facts:
        return ""
    lines = ["<о_человеке>"]
    if name:
        lines.append(f"С тобой говорит {name}" + (f" (его могут звать {', '.join(aka)})" if aka else "") + ".")
    if facts:
        lines.append("Что ты о нём знаешь: " + "; ".join(facts[-limit_facts:]) + ".")
    lines.append("Держись с ним как со знакомым, но не пересказывай ему эту справку.")
    lines.append("</о_человеке>")
    return "\n".join(lines)


def known_here(chat_id: str, *, limit: int = 12) -> str:
    """Короткая подсказка для группы: кого она тут уже знает."""
    chat_id = str(chat_id or "")
    if not chat_id:
        return ""
    names = []
    for person in (_load().get("people") or {}).values():
        if chat_id in (person.get("chats") or []) and person.get("name"):
            names.append(person["name"])
    if not names:
        return ""
    return "В этом чате ты уже знаешь: " + ", ".join(sorted(set(names))[:limit]) + "."


def log_line(user_id: Any, name: str, text: str, *, chat_id: str, chat_title: str = "",
             role: str = "user") -> None:
    """Строка чата для последующей синхронизации фактов (people_sync)."""
    text = " ".join(str(text or "").split())
    if not text and role == "user":
        return
    record = {"ts": int(time.time()), "chat": str(chat_id or ""), "chat_title": str(chat_title or "")[:60],
              "uid": _key(user_id), "name": " ".join(str(name or "").split()), "role": role,
              "text": text[:600]}
    try:
        if LINES.exists() and LINES.stat().st_size > MAX_LINE_BYTES:
            LINES.replace(LINES.with_suffix(".jsonl.old"))
        with LINES.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        log.debug("строку чата не записала: %s", exc)


def split_marker(text: str) -> tuple[str, list[tuple[Optional[str], str]]]:
    """Вытащить из её ответа пометки ``[[запомнить: …]]`` и вернуть текст без них.

    Тело пометки: либо ``Борис — играет на гитаре``, либо просто ``играет на гитаре`` (тогда
    человек — тот, с кем она сейчас говорит).
    """
    raw = str(text or "")
    notes: list[tuple[Optional[str], str]] = []
    for match in MARKER.finditer(raw):
        body = " ".join(match.group("body").split())
        if not body:
            continue
        head, sep, tail = body.partition(" — ")
        if sep and len(head.split()) <= 3:
            notes.append((head.strip(), tail.strip()))
        else:
            parts = _DASH.split(body, maxsplit=1)
            if len(parts) == 2 and len(parts[0].split()) <= 3:
                notes.append((parts[0].strip(), parts[1].strip()))
            else:
                notes.append((None, body))
    return MARKER.sub("", raw).strip(), notes
