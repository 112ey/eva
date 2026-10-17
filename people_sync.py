"""Ева (fork): синхронизация «кто есть кто» из чатов в карточки людей.

Строки чатов копятся адаптером в ``~/eva-home/chat_lines.jsonl`` (группа и личка — все вместе).
Этот скрипт раз в пару часов догоняет новые строки, спрашивает модель «что тут устойчивые факты о
человеке» и дописывает их в карточки (``eva_people.remember``). Дальше карточка сама уезжает в
промт: в группе — про того, кто написал, в личке — про собеседника. Поэтому услышанное в группе
она знает и в личке.

Запуск: ``eva --run-module people_sync`` (обычно из таймера), ``--dry`` — только показать, что
нашлось бы, ничего не записывая, ``--since-minutes N`` — окно разбора.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, "/home/iizey/eva-hermes")

import eva_people  # noqa: E402

log = logging.getLogger("eva.people_sync")

HOME = Path(os.environ.get("HERMES_HOME") or (Path.home() / "eva-home"))
STATE = HOME / "people_sync_state.json"
BATCH_LINES = 40
MODEL_TIMEOUT = 60.0
MAX_FACTS_PER_RUN = 3

SYSTEM = (
    "Ты разбираешь строки телеграм-чата и выделяешь то, что стоит запомнить о человеке надолго: "
    "кто он, чем занимается, увлечения, привычки, важные события в его жизни, отношения с другими. "
    "Не запоминай разовое: реплики о погоде, мемы, «ок», «ахахах», сиюминутные планы, грубость в "
    "перепалке. Если факт уже известен из списка известного — не повторяй. "
    "Ответ — до трёх пунктов, каждый с новой строки, коротко, без нумерации и пояснений. "
    "Если запоминать нечего — ответь одним словом: нет."
)


def _load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"offset": 0, "facts_total": 0}


def _save_state(state: dict) -> None:
    try:
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        log.warning("состояние синхронизации не сохранить: %s", exc)


def _read_new_lines(offset: int) -> tuple[list[dict], int]:
    path = eva_people.LINES
    if not path.exists():
        return [], offset
    size = path.stat().st_size
    if size < offset:            # файл ротировался — читаем с начала
        offset = 0
    rows: list[dict] = []
    with path.open("rb") as handle:
        handle.seek(offset)
        for raw in handle.readlines():
            try:
                rows.append(json.loads(raw.decode("utf-8")))
            except (ValueError, UnicodeDecodeError):
                continue
        new_offset = handle.tell()
    return rows, new_offset


def _ask(about: str, known: list[str], lines: list[str]) -> list[str]:
    """Спросить модель, что нового о человеке. Пусто — не удалось или нечего."""
    from plugins.platforms.telegram.eva_gate import (_call, _endpoint, resolve_fallback,
                                                     resolve_reasoning_effort, resolve_target)
    provider, model, base_url = resolve_target()
    if not model:
        return []
    user = (
        (f"Известное о человеке:\n" + "\n".join(f"- {fact}" for fact in known) + "\n\n" if known else "")
        + f"Строки чата ({about}):\n" + "\n".join(lines) + "\n\n"
        + "Что запомнить об этом человеке надолго? До трёх пунктов, каждый с новой строки, "
          "или одно слово: нет."
    )
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
    effort = resolve_reasoning_effort()
    answer = None
    base, key = _endpoint(provider, base_url)
    if base and key:
        answer = _call(base, key, model, messages, timeout=MODEL_TIMEOUT, reasoning_effort=effort,
                       max_tokens=400)
    if answer is None:
        fb_provider, fb_model, fb_base = resolve_fallback()
        fb_url, fb_key = _endpoint(fb_provider, fb_base)
        if fb_model and fb_url and fb_key:
            answer = _call(fb_url, fb_key, fb_model, messages, timeout=MODEL_TIMEOUT,
                           reasoning_effort=effort, max_tokens=400)
    if not answer:
        return []
    text = " ".join(str(answer).split())
    if re.fullmatch(r"(?i)(нет|нечего|no)\.?", text):
        return []
    facts = []
    for chunk in re.split(r"(?:\n|(?<=\.)\s(?=[А-ЯA-Z]))", str(answer)):
        item = chunk.strip().lstrip("-•*0123456789. )").strip()
        if len(item) < 8 or len(item) > 200:
            continue
        if re.fullmatch(r"(?i)(нет|нечего|no)\.?", item):
            continue
        facts.append(item)
    return facts[:MAX_FACTS_PER_RUN]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry", action="store_true", help="ничего не записывать")
    parser.add_argument("--since-minutes", type=int, default=180, help="окно разбора, минуты")
    parser.add_argument("--limit-people", type=int, default=6, help="сколько человек за прогон")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    state = _load_state()
    rows, new_offset = _read_new_lines(int(state.get("offset") or 0))
    cutoff = time.time() - args.since_minutes * 60
    rows = [row for row in rows if int(row.get("ts") or 0) >= cutoff and row.get("uid")]
    if not rows:
        print("новых строк нет — синхронизировать нечего")
        if not args.dry:
            _save_state({**state, "offset": new_offset, "checked_at": int(time.time())})
        return 0

    by_person: dict[str, list[dict]] = {}
    for row in rows:
        by_person.setdefault(str(row["uid"]), []).append(row)
    print(f"новых строк: {len(rows)}, людей: {len(by_person)}")
    stored = 0
    for index, (uid, person_rows) in enumerate(sorted(by_person.items(),
                                                      key=lambda item: item[1][-1]["ts"], reverse=True)):
        if index >= args.limit_people:
            break
        name = next((row.get("name") for row in reversed(person_rows) if row.get("name")), "")
        chat_title = next((row.get("chat_title") for row in reversed(person_rows) if row.get("chat_title")), "")
        current = (((eva_people._load().get("people") or {}).get(uid)) or {})
        known = [f.get("text") for f in (current.get("facts") or []) if f.get("text")]
        lines = [f"{row.get('name') or uid}: {row.get('text')}" for row in person_rows[-BATCH_LINES:]]
        about = f"{name or uid}" + (f", чат «{chat_title}»" if chat_title else "")
        facts = _ask(about, known, lines)
        if not facts:
            print(f"  {name or uid}: нового нет")
            continue
        for fact in facts:
            if args.dry:
                print(f"  {name or uid}: (dry) {fact}")
                continue
            if eva_people.remember(uid, fact, source=chat_title or "чат", name=name):
                stored += 1
                print(f"  {name or uid}: + {fact}")
    if not args.dry:
        _save_state({"offset": new_offset, "facts_total": int(state.get("facts_total") or 0) + stored,
                     "checked_at": int(time.time())})
    print(f"готово: записано фактов {stored}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
