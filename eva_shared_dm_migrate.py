"""Перевести её личку на общий ключ сессии, не потеряв историю.

Зачем: с включённым ``extra.shared_dm_session`` лички всех разрешённых собеседников идут в одну
сессию с ключом ``agent:main:telegram:dm:shared``. Но у уже существующей лички владельца ключ
другой (``…:dm:<его id>``), поэтому без переноса её разговор начался бы с чистого листа.

Что делает скрипт: берёт строку маршрутизации владельца из ``gateway_routing``, кладёт её же
копию под общим ключом (та же ``session_id`` — та же история), и проверяет результат через настоящий
стор гейтвея. Идемпотентно: повторный запуск ничего не ломает.

    python3 eva_shared_dm_migrate.py            # показать план
    python3 eva_shared_dm_migrate.py --apply    # перенести
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, "/home/iizey/eva-hermes")

HOME = Path(os.environ.get("HERMES_HOME") or (Path.home() / "eva-home"))
DB = HOME / "state.db"
OWNER_KEY = "agent:main:telegram:dm:111111111"
SHARED_KEY = "agent:main:telegram:dm:shared"


def row_for(key: str):
    if not DB.exists():
        return None
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        return conn.execute(
            "SELECT scope, session_key, entry_json, updated_at FROM gateway_routing WHERE session_key = ?",
            (key,)).fetchone()
    finally:
        conn.close()


def backup() -> Path | None:
    if not DB.exists():
        return None
    target = HOME / "diary_backups" / f"state_{time.strftime('%Y%m%d_%H%M%S')}.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(DB)
    try:
        dest = sqlite3.connect(target)
        try:
            source.backup(dest)
        finally:
            dest.close()
    finally:
        source.close()
    return target


def copy_row(owner_row, apply: bool) -> bool:
    scope, _, entry_json, updated_at = owner_row
    data = json.loads(entry_json)
    data["session_key"] = SHARED_KEY
    payload = json.dumps(data, ensure_ascii=False)
    if not apply:
        print(f"будет создана строка {SHARED_KEY} -> session_id={data.get('session_id')}")
        return True
    conn = sqlite3.connect(DB)
    try:
        conn.execute(
            "INSERT INTO gateway_routing (scope, session_key, entry_json, updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(scope, session_key) DO UPDATE SET entry_json=excluded.entry_json, updated_at=excluded.updated_at",
            (scope, SHARED_KEY, payload, updated_at or time.time()))
        conn.commit()
    finally:
        conn.close()
    return True


def verify() -> bool:
    """Проверка через настоящий билдер ключа: и личка владельца, и чужая ведут в общий ключ."""
    from gateway.session import Platform, SessionSource, build_session_key

    def dm(user_id: str):
        return SessionSource(platform=Platform.TELEGRAM, chat_id=user_id, chat_type="dm",
                             user_id=user_id, user_name="кто-то")

    owner_key = build_session_key(dm("111111111"))
    other_key = build_session_key(dm("333333333"))
    mapped = row_for(owner_key)
    print(f"ключ владельца: {owner_key}")
    print(f"ключ знакомого: {other_key}")
    if mapped:
        print(f"в этот ключ смотрит session_id={json.loads(mapped[2]).get('session_id')} — история на месте")
    return owner_key == other_key == SHARED_KEY and mapped is not None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    owner_row = row_for(OWNER_KEY)
    shared_row = row_for(SHARED_KEY)
    if owner_row is None and shared_row is None:
        print("нет ни строки владельца, ни общей — переносить нечего (первая личка создастся сразу общей)")
        return 0
    if shared_row is not None:
        print(f"общая строка уже есть: session_id={json.loads(shared_row[2]).get('session_id')}")
        return 0
    if owner_row is None:
        print("строки владельца нет — ему личка создастся уже под общим ключом")
        return 0
    print(f"личка владельца: session_id={json.loads(owner_row[2]).get('session_id')}")
    if args.apply:
        path = backup()
        print(f"бэкап базы: {path}")
    copy_row(owner_row, args.apply)
    if args.apply:
        ok = verify()
        print("перенос:", "ок" if ok else "НЕ УДАЛСЯ")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
