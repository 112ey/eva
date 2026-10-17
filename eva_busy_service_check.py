"""Проверка: служебные отписки о занятости не попадают в её чат.

Ловушка, которую ловим: галочка display.*.busy_steer_ack_enabled в форке глушила только режим steer,
а «↪ Текущий запуск перенаправлен» (redirect) и «⏳ в очереди» шли в чат мимо неё.
"""
import asyncio
import sys
import types

sys.path.insert(0, "/home/iizey/eva-hermes")

from gateway.run_busy import GatewayBusySessionMixin  # noqa: E402
from gateway.platforms.event import MessageEvent, MessageType  # noqa: E402
from gateway.session import Platform, SessionSource  # noqa: E402

fail = []


def check(name, cond, extra=""):
    print(f"[{'ok' if cond else 'FAIL'}] {name}{' — ' + str(extra) if extra else ''}")
    if not cond:
        fail.append(name)


class Adapter:
    def __init__(self):
        self.sent = []

    async def _send_with_retry(self, chat_id, content, reply_to=None, metadata=None):
        self.sent.append(content)
        return types.SimpleNamespace(ok=True)


class Stub(GatewayBusySessionMixin):
    """Заглушка гейтвея: доходим до отправки отписки, не поднимая настоящий шлюз."""

    def __init__(self, redirect=True, ack_enabled=None):
        self.adapter = Adapter()
        self._draining = False
        self.redirect = redirect
        self._ack_override = ack_enabled
        self.queued = []
        self._pending_messages = {}
        self._restart_requested = False
        self.config = types.SimpleNamespace(extra={})

    def _status_action_gerund(self):
        return "перезапускается"

    def _reply_anchor_for_event(self, event):
        return None

    def _busy_reply_to(self, event, anchor):
        return None

    def _thread_metadata_for_source(self, source, anchor):
        return {}

    # --- то, что вызывается по пути ---
    def _delivery_adapter_for(self, source):
        return self.adapter

    def _is_user_authorized_for_source(self, source):
        return True

    def _admit_bot_message_for_source(self, source):
        return True

    def _effective_busy_input_mode(self, source):
        return "interrupt"

    def _effective_busy_text_mode(self, source):
        return "interrupt"

    def _peek_session_state(self, key):
        return None

    def _session_state(self, key):
        return types.SimpleNamespace(turn=types.SimpleNamespace(busy_ack_ts=0.0, agent=None, started_ts=0.0))

    def _busy_steer_ack_enabled(self, event, session_key):
        if self._ack_override is not None:
            return self._ack_override
        return False  # как в её конфиге: display.platforms.telegram.busy_steer_ack_enabled=false

    async def _resolve_busy_steer_or_redirect(self, event, session_key, effective_mode, running_agent):
        return types.SimpleNamespace(
            effective_mode="interrupt", redirected=self.redirect, steered=self.redirect,
            demoted_for_subagents=False, demoted_for_compression=False)

    def _queue_or_replace_pending_event(self, session_key, event):
        self.queued.append(event)

    def _agent_has_active_subagents(self, agent):
        return False

    def _interrupt_running_agent_for_busy_event(self, event, adapter, running_agent):
        return asyncio.sleep(0)

    def _route_plaintext_approval_while_busy(self, event, session_key):
        return asyncio.sleep(0)


def event():
    src = SessionSource(
        platform=Platform.TELEGRAM, chat_id="-1002222222222", chat_type="group",
        user_id="111111111", user_name="Владелец", thread_id="9245")
    return MessageEvent(text="Ева, а как тебе это?", message_type=MessageType.TEXT, source=src)


def run(stub):
    try:
        return asyncio.run(GatewayBusySessionMixin._handle_active_session_busy_message(stub, event(), "key"))
    except Exception as exc:  # noqa: BLE001 — показываем причину, а не только «не ушло»
        print(f"   !! ход занятости упал: {type(exc).__name__}: {str(exc)[:160]}")
        return None


# 1. Перенаправление хода: в чат ничего
stub = Stub(redirect=True)
handled = run(stub)
check("redirect: ход обработан", handled is True, handled)
check("redirect: в чат ничего не ушло", stub.adapter.sent == [], stub.adapter.sent)

# 2. Очередь (обычное сообщение во время хода): тоже тишина
stub = Stub(redirect=False)
run(stub)
check("очередь: в чат ничего не ушло", stub.adapter.sent == [], stub.adapter.sent)

# 3. Контроль: если галочку включить — отписка отправляется (проверка, что тест умеет ловить отправку)
stub = Stub(redirect=True, ack_enabled=True)
run(stub)
check("с включённой галочкой отписка уходит (контроль)", len(stub.adapter.sent) == 1 and "↪" in stub.adapter.sent[0],
      stub.adapter.sent)

# 4. Отписка при перезапуске шлюза
stub = Stub()
stub._restart_requested = True          # идёт перезапуск, сообщение должно встать в очередь
asyncio.run(GatewayBusySessionMixin._send_busy_drain_notice(stub, event(), "key", "queue"))
check("перезапуск шлюза: в чат ничего не ушло", stub.adapter.sent == [], stub.adapter.sent)
check("перезапуск шлюза: сообщение поставлено в очередь", len(stub.queued) == 1, len(stub.queued))

# 5. Старый ключ только для steer больше не спасает: проверяем, что галочка глушит и redirect, и queue
check("в форке нет steer-only условия", "is_steer_mode and not self._busy_steer_ack_enabled" not in
      open("/home/iizey/eva-hermes/gateway/run_busy.py", encoding="utf-8").read())

print("\nBUSY-SERVICE", "PASSED" if not fail else f"FAILED: {fail}")
sys.exit(1 if fail else 0)
