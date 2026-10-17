"""Проверка ручного выключателя: /fuckingstop и /fuckingcontinue (только владелец, без сброса сессии)."""
import asyncio
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, "/home/iizey/eva-hermes")
sys.path.insert(0, "/home/iizey/eva-home")

import eva_control  # noqa: E402
from plugins.platforms.telegram.adapter import TelegramAdapter  # noqa: E402

fail = []
OWNER = 111111111
STRANGER = 333333333

tmp = Path(tempfile.mkdtemp())
eva_control.STATE = tmp / "control.json"


def check(name, cond, extra=""):
    print(f"[{'ok' if cond else 'FAIL'}] {name}{' — ' + str(extra) if extra else ''}")
    if not cond:
        fail.append(name)


def command(text, user_id=OWNER):
    return types.SimpleNamespace(
        text=text, message_id=99, chat=types.SimpleNamespace(id=-1001111111111),
        from_user=types.SimpleNamespace(id=user_id, full_name="Владелец"))


class Bot:
    def __init__(self):
        self.reactions = []

    async def set_message_reaction(self, chat_id=None, message_id=None, reaction=None):
        self.reactions.append((chat_id, message_id, reaction))
        return True


class _Stub(TelegramAdapter):
    name = "Telegram"


stub = object.__new__(_Stub)
stub._bot = Bot()
stub.config = types.SimpleNamespace(extra={"eva_control": {"owner_ids": [str(OWNER)]}})
stub._eva_muted_cache = None
stub.sent_confirmations = []


async def _fake_send(chat_id, content, reply_to=None, metadata=None):
    stub.sent_confirmations.append(content)
    return types.SimpleNamespace(success=True, message_id="1")


stub.send = _fake_send
stub._event_thread_metadata = lambda event, source: None

# 1. Файл состояния
check("по умолчанию не заткнута", eva_control.is_muted() is False)
eva_control.set_muted(True, by=str(OWNER))
check("состояние пишется в файл", eva_control.is_muted() is True)
eva_control.set_muted(False)
check("состояние снимается", eva_control.is_muted() is False)

# 2. Команда владельца работает, состояние переключается, сессия не трогается
handled = asyncio.run(TelegramAdapter._eva_handle_control_command(stub, command("/fuckingstop"), None))
check("команда поймана (stop)", handled is True)
check("после stop она заткнута", eva_control.is_muted() is True)
check("подтверждение — реакция 🙊", stub._bot.reactions[-1][2] == "🙊", stub._bot.reactions[-1])
check("в чат при этом ничего не пишет", stub.sent_confirmations == [], stub.sent_confirmations)

handled = asyncio.run(TelegramAdapter._eva_handle_control_command(stub, command("/fuckingcontinue@evachan_bot_bot"), None))
check("команда с @ботом тоже ловится", handled is True)
check("после continue она снова пишет", eva_control.is_muted() is False)
check("подтверждение — реакция 👀", stub._bot.reactions[-1][2] == "👀", stub._bot.reactions[-1])

# 3. Чужая команда игнорируется и состояние не меняет
handled = asyncio.run(TelegramAdapter._eva_handle_control_command(stub, command("/fuckingstop", STRANGER), None))
check("чужая команда поймана, но не выполнена", handled is True)
check("чужой не может заткнуть", eva_control.is_muted() is False)
check("реакций от чужой попытки нет", len(stub._bot.reactions) == 2, stub._bot.reactions)

# 3b. В группе команда работает даже без упоминания (require_mention её не режет)
eva_control.set_muted(False)
stub._eva_muted_cache = None


def _must_not_gate(message, *, is_command=False):
    raise AssertionError("до проверки упоминания дело доходить не должно")


stub._should_process_message = _must_not_gate
stub._effective_update_message = lambda update: command("/fuckingstop")
try:
    asyncio.run(TelegramAdapter._handle_command(stub, object(), None))
    check("команда без упоминания в группе срабатывает", eva_control.is_muted() is True)
except AssertionError as exc:
    check("команда без упоминания в группе срабатывает", False, str(exc))
eva_control.set_muted(False)
stub._eva_muted_cache = None

# 4. Не её команда не перехватывается
check("другая команда идёт обычным путём",
      asyncio.run(TelegramAdapter._eva_handle_control_command(stub, command("/start"), None)) is False)

# 4b. Служебные команды — только владельцу
stub._should_process_message = lambda message, is_command=False: True   # гейт упоминания уже проверен выше
stub.config = types.SimpleNamespace(extra={"eva_control": {"owner_ids": [str(OWNER)], "owner_only_commands": True},
                                           "allow_from": [str(OWNER), str(STRANGER)]})
stub._is_user_authorized_from_message = lambda msg: True
dispatched = []
stub._ensure_forum_commands = lambda message: _noop()
async def _fake_event(*args, **kwargs):
    return types.SimpleNamespace(text="x")


stub._build_triggered_event = _fake_event
stub.handle_message = lambda event: dispatched.append("agent") or _noop()
stub._effective_update_message = lambda update: command("/reset", STRANGER)


async def _noop():
    return None


asyncio.run(TelegramAdapter._handle_command(stub, object(), None))
check("чужой не может сбросить сессию (/reset)", dispatched == [], dispatched)

stub._effective_update_message = lambda update: command("/reset", OWNER)
asyncio.run(TelegramAdapter._handle_command(stub, object(), None))
check("владельцу служебные команды по-прежнему можно", dispatched == ["agent"], dispatched)

stub.config.extra["eva_control"]["owner_only_commands"] = False
dispatched.clear()
stub._effective_update_message = lambda update: command("/reset", STRANGER)
asyncio.run(TelegramAdapter._handle_command(stub, object(), None))
check("ключом можно вернуть команды всем", dispatched == ["agent"], dispatched)
stub.config.extra["eva_control"]["owner_only_commands"] = True

# 5. Заткнутая: сообщения не доходят до хода
eva_control.set_muted(True, by=str(OWNER))
stub._eva_muted_cache = None
called = []
stub._effective_update_message = lambda update: command("привет")
stub._is_user_authorized_from_message = lambda msg: True
stub._gate_or_observe = lambda *a, **k: called.append("gate") or True
asyncio.run(TelegramAdapter._handle_text_message(stub, object(), None))
check("заткнутая не открывает ход", called == [], called)

eva_control.set_muted(False)
stub._eva_muted_cache = None
stub._enqueue_text_event = lambda event: called.append("enqueue")
stub._gate_or_observe = lambda *a, **k: called.append("gate") or False
asyncio.run(TelegramAdapter._handle_text_message(stub, object(), None))
check("после continue ход снова открывается", "gate" in called, called)

# 6. Заткнутая: ни одно сообщение не уходит в чат
stub._reply_to_mode = "off"


async def _text_ok(chat_id, content, reply_to=None, metadata=None):
    stub.sent_confirmations.append(content)
    return types.SimpleNamespace(success=True, message_id="1")


stub._send_text_locked = _text_ok


class _null_lock:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc):
        return False


stub._chat_send_lock = lambda chat_id: _null_lock()
eva_control.set_muted(True, by=str(OWNER))
stub._eva_muted_cache = None
result = asyncio.run(TelegramAdapter.send(stub, "-1001111111111", "привет"))
check("send при мьюте отменяется", result.success is False and "muted" in str(result.error), result)
result = asyncio.run(TelegramAdapter.send(stub, "-1001111111111", "молчу.",
                                          metadata={"_eva_control_confirm": True}))
check("подтверждение команды проходит мимо мьюта", result.success is True, result)
eva_control.set_muted(False)
stub._eva_muted_cache = None

# 7. Таймер молчит, пока её заткнули
import proactive_gate  # noqa: E402

eva_control.set_muted(True, by=str(OWNER))
allowed, reason = proactive_gate.decide()
check("таймер не пишет при мьюте", allowed is False and "fuckingstop" in reason, reason)
eva_control.set_muted(False)

print("\nCONTROL", "PASSED" if not fail else f"FAILED: {fail}")
sys.exit(1 if fail else 0)
