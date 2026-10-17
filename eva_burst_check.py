"""Проверка всплесков: десяток реплик подряд → один её ответ, и фильтр спрошен один раз."""
import asyncio
import sys
import time
import types

sys.path.insert(0, "/home/iizey/eva-hermes")

from plugins.platforms.telegram.adapter import TelegramAdapter  # noqa: E402
from gateway.platforms.event import MessageType  # noqa: E402

fail = []
CHAT = "-1002222222222"


def check(name, cond, extra=""):
    print(f"[{'ok' if cond else 'FAIL'}] {name}{' — ' + str(extra) if extra else ''}")
    if not cond:
        fail.append(name)


def message(text, user_id=222222222, name="boris_nick", message_id=100):
    return types.SimpleNamespace(
        chat=types.SimpleNamespace(id=int(CHAT), type="supergroup", title="Тестовая группа"),
        from_user=types.SimpleNamespace(id=user_id, full_name=name, is_bot=False),
        message_id=message_id, text=text, caption=None, quote=None, reply_to_message=None,
        message_thread_id=1, date=None)


class _Stub(TelegramAdapter):
    name = "Telegram"

    def __init__(self, window=0.5, max_wait=1.2, addressed=False, gate=True):
        self.config = types.SimpleNamespace(extra={"eva_burst_window_seconds": window,
                                                  "eva_burst_max_wait_seconds": max_wait})
        self.dispatched = []
        self.dispatch_times = []
        self.observed = []
        self.gate_calls = []
        self._addressed = addressed
        self._gate = gate

    # минимально нужное окружение
    def _is_group_chat(self, msg):
        return True

    def _chat_id_str(self, msg):
        return str(msg.chat.id)

    def _is_reply_to_bot(self, msg):
        return self._addressed and "ей" in (msg.text or "")

    def _message_mentions_bot(self, msg):
        return False

    def _message_matches_mention_patterns(self, msg):
        return False

    def _eva_remember_group_line(self, msg):
        self.gate_calls.append(("remember", getattr(msg, "text", "")))

    def _eva_gate_lines(self, chat_id):
        return ["[boris_nick] раньше"]

    def _eva_gate_classify(self, msg, merged=None):
        self.gate_calls.append(("gate", merged))
        return ("reply" if self._gate else "silent"), ""

    def _eva_react_to_message(self, msg, emoji):
        self.gate_calls.append(("react", emoji))
        return True

    async def _ensure_forum_commands(self, msg):
        return None

    async def _build_triggered_event(self, msg, update, msg_type):
        ev = types.SimpleNamespace(text=getattr(msg, "text", ""), reply_expected=True,
                                   source=types.SimpleNamespace(chat_id=CHAT), message_id=str(msg.message_id))
        return ev

    def _eva_attach_recall(self, event):
        return event

    def _enqueue_text_event(self, event):
        self.dispatched.append(event)
        self.dispatch_times.append(time.monotonic())

    def _observe_unmentioned_group_message(self, msg, msg_type, update_id=None):
        self.observed.append((msg.text, update_id))


def update(index=0):
    return types.SimpleNamespace(update_id=index)


async def run_burst(stub, texts, gap=0.05):
    for index, text in enumerate(texts):
        stub._eva_burst_append(message(text, message_id=100 + index), update(index))
        await asyncio.sleep(gap)
    # ждём, пока таймер отработает
    await asyncio.sleep(stub.config.extra["eva_burst_window_seconds"] + 0.6)


# 1. Десяток реплик → один ход, все реплики внутри
stub = _Stub()
texts = [f"реплика {n}" for n in range(1, 11)]
asyncio.run(run_burst(stub, texts))
check("на пачку из 10 реплик — один ход", len(stub.dispatched) == 1, len(stub.dispatched))
merged = stub.dispatched[0].text if stub.dispatched else ""
check("в ход попали все реплики", all(f"реплика {n}" in merged for n in range(1, 11)), merged[:120])
check("реплики подписаны автором", merged.count("[boris_nick|222222222]") == 10, merged.count("["))
check("фильтр спрошен один раз на пачку", sum(1 for kind, _ in stub.gate_calls if kind == "gate") == 1,
      stub.gate_calls)
check("в окно фильтра реплики всё равно попали",
      sum(1 for kind, _ in stub.gate_calls if kind == "remember") == 10, len(stub.gate_calls))

# 2. Реплика к ней в пачке → ход открывается даже если фильтр против
stub = _Stub(addressed=True, gate=False)
asyncio.run(run_burst(stub, ["слушай", "ей, вопрос", "ну?"]))
check("обращение внутри пачки важнее фильтра", len(stub.dispatched) == 1 and not stub.observed,
      (len(stub.dispatched), stub.observed))

# 3. Болтовня без обращения и фильтр против → пачка уходит в наблюдение, ответа нет
stub = _Stub(gate=False)
asyncio.run(run_burst(stub, ["ахах", "ну да", "лан"]))
check("болтовня не открывает ход", stub.dispatched == [] and len(stub.observed) == 1, (stub.dispatched, stub.observed))

# 4. Поток не прекращается: срабатывает потолок ожидания, а не бесконечное накопление
stub = _Stub(window=3.0, max_wait=1.2, addressed=True)
started = time.monotonic()
asyncio.run(run_burst(stub, ["раз", "два", "три", "четыре", "пять", "шесть"], gap=0.5))
first_dispatch = stub.dispatch_times[0] - started if stub.dispatch_times else 99
check("при непрерывном потоке она всё равно отвечает", len(stub.dispatched) >= 1, len(stub.dispatched))
check("первый ответ не позже потолка ожидания", first_dispatch <= 1.8, f"{first_dispatch:.2f}с")
check("шесть реплик — не шесть ответов", len(stub.dispatched) <= 3, len(stub.dispatched))
check("в первую пачку попало то, что успело прийти",
      "раз" in stub.dispatched[0].text and stub.dispatched[0].text.count("[boris_nick") >= 2,
      stub.dispatched[0].text[:120])

# 5. Одиночное сообщение: пачка не ломает обычный случай, но отвечает после окна тишины
stub = _Stub(window=0.3)
started = time.monotonic()
asyncio.run(run_burst(stub, ["одна реплика"], gap=0.01))
elapsed = time.monotonic() - started
check("одиночное сообщение обрабатывается как раньше", len(stub.dispatched) == 1, len(stub.dispatched))
check("но с небольшой задержкой (ждём, не допишет ли ещё)", elapsed >= 0.3, f"{elapsed:.2f}с")

# 6. Выключенные пачки — поведение как раньше (сразу)
stub = _Stub(window=0)
taken = stub._eva_burst_append(message("привет"), update())
check("при window=0 пачки выключены", taken is False)

print("\nBURST", "PASSED" if not fail else f"FAILED: {fail}")
sys.exit(1 if fail else 0)
