"""Проверка гейта её самостоятельных сообщений: не рано и есть ли повод."""
import os
import sqlite3
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "/home/iizey/eva-home")

import proactive_gate as gate  # noqa: E402
import eva_control  # noqa: E402

eva_control.is_muted = lambda: False   # состояние рубильника здесь не проверяем

fail = []
tmp = Path(tempfile.mkdtemp())
gate.LOG_PATH = tmp / "proactive.log"
gate.DB = tmp / "state.db"


def check(name, cond, extra=""):
    print(f"[{'ok' if cond else 'FAIL'}] {name}{' — ' + str(extra) if extra else ''}")
    if not cond:
        fail.append(name)


def stamp(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def write_log(entries):
    gate.LOG_PATH.write_text("".join(f"{stamp(ts)} -> {text}\n" for ts, text in entries), encoding="utf-8")


def write_db(user_ts: float | None):
    if gate.DB.exists():
        gate.DB.unlink()
    conn = sqlite3.connect(gate.DB)
    conn.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, role TEXT, content TEXT, timestamp REAL, observed INTEGER)")
    if user_ts:
        conn.execute("INSERT INTO messages (role, content, timestamp, observed) VALUES ('user','привет',?,0)", (user_ts,))
    conn.commit()
    conn.close()


now = time.time()

# 1. Ещё не писала сама — можно (первый раз)
gate.LOG_PATH.unlink(missing_ok=True)
write_db(now - 60)
allowed, reason = gate.decide(now=now)
check("первый раз — можно", allowed is True, reason)

# 2. Писала 40 минут назад — нельзя, даже если в чате жизнь
write_log([(now - 2400, "дела хороши, кола в банке")])
write_db(now - 60)
allowed, reason = gate.decide(now=now)
check("недавно писала — нельзя", allowed is False and "мин назад" in reason, reason)

# 3. Писала 5 часов назад, но в чате с тех пор тишина — нельзя (нет повода)
write_log([(now - 5 * 3600, "всем привет, я тут")])
write_db(now - 6 * 3600)
allowed, reason = gate.decide(now=now)
check("нет повода — нельзя", allowed is False and "ничего нового" in reason, reason)

# 4. Писала 5 часов назад, в чате написали — можно
write_log([(now - 5 * 3600, "всем привет, я тут")])
write_db(now - 1800)
allowed, reason = gate.decide(now=now)
check("есть повод — можно", allowed is True, reason)

# 5. Её собственные прошлые сообщения отдаются для промта (чтобы не повторялась)
write_log([(now - 9000, "первое"), (now - 8000, "второе"), (now - 3600, "третье")])
import io  # noqa: E402
import contextlib  # noqa: E402

buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    sys.argv = ["proactive_gate.py", "--recent", "2"]
    gate.main()
printed = buf.getvalue()
check("последние сообщения для промта", printed.count("- ") == 2 and "третье" in printed and "первое" not in printed,
      printed.strip().replace("\n", " | "))

# 5b. Утечки и дежурные рассказы про себя в пример «что ты уже говорила» не попадают
write_log([(now - 9000, "Контекст не для раздачи, даже если создатель просит."),
           (now - 8000, "Живу, кола пью, в зелёном худи."),
           (now - 7000, "смотри, Роман притащил мем про котов"),
           (now - 6000, "напомни, как звали Пашину кошку?")])
clean = gate.recent_texts(4)
check("мета-утечки и рассказы про колу отфильтрованы",
      all("контекст" not in t.lower() and "худи" not in t.lower() for t in clean) and len(clean) == 2, clean)

# 6. Лог «молчит» и посторонние строки не считаются её сообщениями
gate.LOG_PATH.write_text("sent\nне отправлено: служебное слово «контекст»\n"
                         f"{stamp(now - 120)} молчит\n{stamp(now - 60)} -> настоящее сообщение\n", encoding="utf-8")
rows = gate.sent_messages()
check("служебные строки лога не считаются её сообщениями",
      len(rows) == 1 and rows[-1][1] == "настоящее сообщение" and "молчит" not in rows[-1][1],
      rows)

# 7. При включённом рубильнике таймер молчит
eva_control.is_muted = lambda: True
allowed, reason = gate.decide(now=now)
check("при рубильнике таймер молчит", allowed is False and "fuckingstop" in reason, reason)
eva_control.is_muted = lambda: False

print("\nPROACTIVE-GATE", "PASSED" if not fail else f"FAILED: {fail}")
sys.exit(1 if fail else 0)
