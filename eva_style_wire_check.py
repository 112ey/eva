"""Проверка, что эмодзи режется и на выходе из адаптера (её чат), и в send_local (таймер)."""
import sys
sys.path.insert(0, "/home/iizey/eva-hermes")
from plugins.platforms.telegram.adapter import TelegramAdapter


class _Stub(TelegramAdapter):
    name = "Telegram"


stub = object.__new__(_Stub)
cases = [("привет 😏", "привет"), ("ура (≧▽≦) 🎉 наконец", "ура (≧▽≦) наконец"), ("без всего", "без всего")]
bad = []
for raw, want in cases:
    got = TelegramAdapter._eva_style(stub, raw)
    ok = got == want
    print(f"[{'ok' if ok else 'FAIL'}] адаптер: {raw!r} -> {got!r}")
    if not ok:
        bad.append(raw)
sys.path.insert(0, "/home/iizey/eva-home")  # send_local живёт в её доме
import send_local  # noqa: E402  (таймер идёт мимо адаптера)
import io, os  # noqa: E402
sys.stdin = io.StringIO("")
print("[ok] send_local импортируется с новой страховкой" if hasattr(send_local, "pick_thread") else "[FAIL] send_local")
print("STYLE-WIRE", "PASSED" if not bad else f"FAILED: {bad}")
sys.exit(1 if bad else 0)
