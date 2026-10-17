"""Karma (Eva fork): a 10-point personal rating she keeps about the people she talks to.

Everyone starts at 5. Only her evening reflection moves it. The numbers are hers alone —
visible to nobody in the group; the owner may ask. Stored as JSON in her own home so it
survives restarts and shows up in her prompt every turn.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.registry import registry

logger = logging.getLogger(__name__)

START = 5
MIN = 0
MAX = 10


def _karma_path() -> Path:
    from hermes_constants import get_hermes_home
    return get_hermes_home() / "karma.json"


def _load() -> dict[str, Any]:
    path = _karma_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("users", {})
            data.setdefault("log", [])
            return data
    except FileNotFoundError:
        pass
    except Exception as exc:
        logger.warning("karma: unreadable store %s: %s", path, exc)
    return {"users": {}, "log": []}


def _save(data: dict[str, Any]) -> None:
    path = _karma_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".karma-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _find(data: dict[str, Any], who: str) -> tuple[str, dict[str, Any]] | None:
    who = (who or "").strip()
    if not who:
        return None
    users = data["users"]
    if who in users:
        return who, users[who]
    lowered = who.casefold()
    for key, entry in users.items():
        if key.casefold() == lowered or str(entry.get("name", "")).casefold() == lowered:
            return key, entry
    return None


def karma_list() -> str:
    """Every person she keeps score on: name, karma, note."""
    data = _load()
    rows = sorted(
        ({"name": entry.get("name") or key, "karma": int(entry.get("karma", START)),
          "note": entry.get("note", ""), "reason": entry.get("reason", "")}
         for key, entry in data["users"].items()),
        key=lambda r: -r["karma"])
    return json.dumps({"success": True, "start": START, "min": MIN, "max": MAX,
                       "people": rows, "count": len(rows)}, ensure_ascii=False)


def karma_set(who: str, delta: int | None = None, value: int | None = None,
              note: str | None = None, reason: str | None = None) -> str:
    """Move one person's karma. `delta` adds/subtracts, `value` overwrites; clamped to 0..10."""
    if value is None and delta is None:
        return json.dumps({"success": False, "error": "нужен delta или value"}, ensure_ascii=False)
    data = _load()
    name = (who or "").strip()
    if not name:
        return json.dumps({"success": False, "error": "нужно имя человека"}, ensure_ascii=False)
    found = _find(data, name)
    key = found[0] if found else name
    entry = found[1] if found else data["users"].setdefault(
        key, {"name": name, "karma": START, "note": "", "created": datetime.now(timezone.utc).isoformat()})
    before = int(entry.get("karma", START))
    after = int(value) if value is not None else before + int(delta or 0)
    after = max(MIN, min(MAX, after))
    entry["karma"] = after
    if note is not None:
        entry["note"] = str(note)[:400]
    # Причина отношения хранится на самом человеке, а не только в логе: блок «## Карма» в промте
    # показывает её, и персона может честно ответить «почему ты со мной так», а не дуться из воздуха.
    if reason is not None:
        entry["reason"] = str(reason)[:300]
    entry["updated"] = datetime.now(timezone.utc).isoformat()
    data["log"].append({"at": entry["updated"], "who": entry.get("name") or key,
                        "from": before, "to": after, "reason": str(reason or "")[:300]})
    data["log"] = data["log"][-400:]
    _save(data)
    return json.dumps({"success": True, "name": entry.get("name") or key,
                       "karma_before": before, "karma_after": after,
                       "note": entry.get("note", "")}, ensure_ascii=False)


KARMA_LIST_SCHEMA = {
    "name": "karma_list",
    "description": ("Кого ты знаешь и как у тебя к ним относится: имя, карма (0–10, у всех "
                    "новичков 5) и твоя заметка. Это твоё личное, вслух не читается."),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

KARMA_SET_SCHEMA = {
    "name": "karma_set",
    "description": ("Поставить или сдвинуть карму человека (0–10). За вечернюю рефлексию — "
                    "по итогам дня: кому-то плюс, кому-то минус. Это твоя оценка, не показывай её в чате."),
    "parameters": {
        "type": "object",
        "properties": {
            "who": {"type": "string", "description": "Имя или @ник человека"},
            "delta": {"type": "integer", "description": "Сдвиг: +1, -2 и т.п. (или используй value)"},
            "value": {"type": "integer", "description": "Поставить точное значение 0–10"},
            "note": {"type": "string", "description": "Твоя заметка о нём — что за человек, что было"},
            "reason": {"type": "string", "description": "За что именно сегодня плюс или минус"},
        },
        "required": ["who"],
    },
}

registry.register(
    name="karma_list", toolset="karma", schema=KARMA_LIST_SCHEMA, emoji="⚖️",
    handler=lambda args, **kw: karma_list())

registry.register(
    name="karma_set", toolset="karma", schema=KARMA_SET_SCHEMA, emoji="⚖️",
    handler=lambda args, **kw: karma_set(who=args.get("who", ""), delta=args.get("delta"),
                                         value=args.get("value"), note=args.get("note"),
                                         reason=args.get("reason")))
