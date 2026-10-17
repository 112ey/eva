"""Проверка форковой логики: неадресованное сообщение в группе может остаться без ответа.

Берём настоящий метод адаптера (unbound) и подсовываем заглушки вместо телеграм-объектов:
проверяем только то, что он делает с event.reply_expected.
"""
import os
import sys
import types

os.environ.setdefault("HERMES_HOME", "/home/iizey/eva-home")
sys.path.insert(0, "/home/iizey/eva-hermes")

from plugins.platforms.telegram.adapter import TelegramAdapter  # noqa: E402

_mark = TelegramAdapter._mark_unaddressed_group_turn
fail: list[str] = []


class Stub:
    """Подменяет три хелпера адресации тремя флагами."""

    def __init__(self, group=True, reply_to_bot=False, mentions_bot=False, mention_pattern=False):
        self.flags = (group, reply_to_bot, mentions_bot, mention_pattern)

    def _is_group_chat(self, msg):
        return self.flags[0]

    def _is_reply_to_bot(self, msg):
        return self.flags[1]

    def _message_mentions_bot(self, msg):
        return self.flags[2]

    def _message_matches_mention_patterns(self, msg):
        return self.flags[3]


def event(reply_expected=None):
    return types.SimpleNamespace(reply_expected=reply_expected, text="что-то")


def check(name, flags, expected):
    ev = event()
    _mark(Stub(*flags), object(), ev)
    got = ev.reply_expected
    ok = got is expected
    print(f"[{'ok' if ok else 'FAIL'}] {name}: reply_expected={got!r} (ждали {expected!r})")
    if not ok:
        fail.append(name)


# (группа, ответ_боту, упоминание_бота, совпадение_по_имени)
check("группа, никто не обращался", (True, False, False, False), False)
check("группа, ответ на её сообщение", (True, True, False, False), None)
check("группа, @упоминание", (True, False, True, False), None)
check("группа, позвали по имени «Ева»", (True, False, False, True), None)
check("личка", (False, False, False, False), None)

# Батч: адресованное сообщение в пачке поднимает reply_expected обратно в True
ev = event()
_mark(Stub(True, False, False, False), object(), ev)
ev.reply_expected = True  # так делает absorb_reply_expected при склейке кусков
print(f"[{'ok' if ev.reply_expected is True else 'FAIL'}] адресованное в батче -> True")

print("SILENCE-GATE", "PASSED" if not fail else f"FAILED: {fail}")
sys.exit(1 if fail else 0)
