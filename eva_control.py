"""Ева (fork): ручной выключатель — /fuckingstop и /fuckingcontinue.

Владелец может заткнуть персону одной командой и вернуть её обратно. Состояние лежит в файле
`<home>/control.json`, а не в памяти процесса: так его видят и адаптер (не отвечать), и таймеры
(не писать сами), и всё это переживает перезапуск шлюза. Сессия при этом НЕ сбрасывается: после
/fuckingcontinue разговор продолжается с того же места, транскрипт не тронут.

CLI для скриптов и таймеров:

    python3 eva_control.py status          # muted | active
    python3 eva_control.py stop --by 123    # заткнуться
    python3 eva_control.py continue         # снова можно писать
    python3 eva_control.py exit-code        # 0 если можно писать, 1 если заткнута
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path


def _home() -> Path:
    """Её дом — всегда тот, где лежат её файлы.

    Ловушка: при ручном запуске из чужой сессии HERMES_HOME может указывать на дом другого профиля,
    и состояние уезжало в папку форка — адаптер читал один файл, CLI писал другой. Поэтому дом
    ищем по маркеру (proactive_target.txt), а не по одной переменной.
    """
    for candidate in (os.environ.get("HERMES_HOME"), str(Path.home() / "eva-home"),
                      str(Path(__file__).resolve().parent)):
        if candidate and (Path(candidate) / "proactive_target.txt").exists():
            return Path(candidate)
    return Path(__file__).resolve().parent


STATE = _home() / "control.json"


def load() -> dict:
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(data: dict) -> None:
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(STATE)
    except OSError:
        pass


def is_muted() -> bool:
    return bool(load().get("muted"))


def set_muted(flag: bool, by: str = "") -> dict:
    data = load()
    data["muted"] = bool(flag)
    data["changed_at"] = int(time.time())
    if by:
        data["by"] = str(by)
    if flag:
        data["since"] = int(time.time())
    else:
        data.pop("since", None)
    save(data)
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["status", "stop", "continue", "exit-code"])
    ap.add_argument("--by", default="")
    args = ap.parse_args()
    if args.action == "stop":
        set_muted(True, by=args.by)
        print("muted")
        return 0
    if args.action == "continue":
        set_muted(False)
        print("active")
        return 0
    muted = is_muted()
    if args.action == "exit-code":
        return 1 if muted else 0
    print("muted" if muted else "active")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
