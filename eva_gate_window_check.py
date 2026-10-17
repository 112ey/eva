"""Проверка окна фильтра: засев из транскрипта и учёт её собственных реплик.

Живого стора не требует — подсовываем заглушку с load_transcript().
"""
import os
import sys
import types

os.environ.setdefault("HERMES_HOME", "/home/iizey/eva-home")
sys.path.insert(0, "/home/iizey/eva-hermes")

from plugins.platforms.telegram.adapter import TelegramAdapter  # noqa: E402

fail: list[str] = []


def check(name, cond, extra=""):
    print(f"[{'ok' if cond else 'FAIL'}] {name}{' — ' + str(extra) if extra else ''}")
    if not cond:
        fail.append(name)


TRANSCRIPT = [
    {"role": "session_meta", "content": "мусор"},
    {"role": "user", "content": "[Паша|111]\nкто-нибудь видел мой зарядник?"},
    {"role": "assistant", "content": "не видела"},
    {"role": "tool", "content": '{"success": true}'},
    {"role": "user", "content": "[Алексей|222]\nя вчера купил кроссовки"},
]


class Store:
    def get_or_create_session(self, source):
        return types.SimpleNamespace(session_id="s1")

    def load_transcript(self, session_id):
        return list(TRANSCRIPT)


class Stub(TelegramAdapter):
    name = "Telegram"

    def __init__(self):
        self._session_store = Store()
        self._eva_recent = {}
        self._eva_seeded = set()
        self.config = types.SimpleNamespace(extra={})

    def _source_from_message_for_auth(self, msg):
        return types.SimpleNamespace(chat_id="-100", user_id="111", user_name="Паша")

    def _telegram_group_observe_shared_source(self, source):
        return source


stub = Stub()
msg = types.SimpleNamespace()

# 1. Засев из транскрипта
TelegramAdapter._eva_seed_gate_lines(stub, "-100", msg)
window = stub._eva_recent["-100"]
check("транскрипт поднят в окно", len(window) == 3, window)
check("наблюдаемая запись сжата до [имя] текст",
      window[0] == "[Паша] кто-нибудь видел мой зарядник?", window[:1])
check("её реплика помечена [Ева]", "[Ева] не видела" in window, window)
check("служебные строки (tool/meta) не попали",
      not any("success" in line or "мусор" in line for line in window), window)

# 2. Идемпотентность
TelegramAdapter._eva_seed_gate_lines(stub, "-100", msg)
check("повторный засев ничего не дублирует", len(stub._eva_recent["-100"]) == 3)

# 3. Живая реплика встаёт после истории
TelegramAdapter._eva_remember_group_line(
    stub, types.SimpleNamespace(text="и чё", caption=None, photo=None,
                                from_user=types.SimpleNamespace(full_name="Алексей"),
                                chat=types.SimpleNamespace(id=-100, type="supergroup"),
                                message_thread_id=None))
check("живая реплика добавилась в конец",
      stub._eva_recent["-100"][-1] == "[Алексей] и чё", stub._eva_recent["-100"][-3:])

# 4. Своя реплика дописывается в уже засеянное окно
TelegramAdapter._eva_note_own_message(stub, "-100", "сама не видела")
check("её живой ответ в окне", stub._eva_recent["-100"][-1] == "[Ева] сама не видела",
      stub._eva_recent["-100"][-2:])

# 5. Незнакомый чат: своё сообщение не создаёт окно с нуля
TelegramAdapter._eva_note_own_message(stub, "-999", "привет")
check("чужой чат окно не создаёт", "-999" not in stub._eva_recent, list(stub._eva_recent))
# ...и в личку тоже не пишем
TelegramAdapter._eva_note_own_message(stub, "111111111", "привет")
check("личка в окно не попадает", "111111111" not in stub._eva_recent, list(stub._eva_recent))

# 6. Кольцо буфера ограничено
TelegramAdapter._eva_remember_group_line(
    stub, types.SimpleNamespace(text="x" * 30, caption=None, photo=None,
                                from_user=types.SimpleNamespace(full_name="Паша"),
                                chat=types.SimpleNamespace(id=-100, type="supergroup"),
                                message_thread_id=None))
check("буфер не растёт бесконечно", len(stub._eva_recent["-100"]) <= 24, len(stub._eva_recent["-100"]))

print("\nGATE-WINDOW", "PASSED" if not fail else f"FAILED: {fail}")
sys.exit(1 if fail else 0)
