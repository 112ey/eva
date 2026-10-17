"""Проверка: служебные строки гейтвея не попадают в её чат (она либо отвечает, либо молчит)."""
import asyncio
import sys
import types
from pathlib import Path

sys.path.insert(0, "/home/iizey/eva-hermes")

from gateway.run_turn import (  # noqa: E402
    _eva_is_service_explainer, _unexpected_silence_reply, GatewayTurnMixin,
)
from agent.i18n import t  # noqa: E402

fail = []


def check(name, cond, extra=""):
    print(f"[{'ok' if cond else 'FAIL'}] {name}{' — ' + str(extra) if extra else ''}")
    if not cond:
        fail.append(name)


# 1. Служебные строки распознаются
service = [
    t("gateway.errors.unexpected_silence"),
    t("gateway.errors.generic_failed"),
    t("gateway.errors.generic_failed_with_hint", hint=""),
    "⚠️ Что-то пошло не так",
    t("explainer.no_reply_prefix") + t("explainer.empty_response", model="Модель"),
]
for text in service:
    check(f"служебное распознано: {text[:42]!r}", _eva_is_service_explainer(text) is True)

# 2. Живые реплики не считаются служебными
for text in ["да ну, с чего ты взял", "(っ✧ω✧)っ норм всё", "ок", "!важно", "вау, круто (≧▽≦)", ""]:
    check(f"живая реплика не тронута: {text[:26]!r}", _eva_is_service_explainer(text) is False)

# 3. Ответ вместо маркера молчания — пустой
check("_unexpected_silence_reply молчит", _unexpected_silence_reply() == "", repr(_unexpected_silence_reply()))


# 4. Сквозная проверка хода: маркер молчания на адресованном сообщении → в чат ничего
class Stub(GatewayTurnMixin):
    def __init__(self):
        self.async_session_store = types.SimpleNamespace(clear_resume_pending=lambda *a, **k: asyncio.sleep(0))
        self._cleared = []

    async def _clear_restart_failure_count(self, key):
        self._cleared.append(key)


stub = object.__new__(Stub)
stub._cleared = []
stub.token = None
stub.sessions = {}
stub.platform_adapters = {}
stub.config = types.SimpleNamespace(extra={})
stub.async_session_store = types.SimpleNamespace(clear_resume_pending=lambda *a, **k: asyncio.sleep(0))

source = types.SimpleNamespace(platform=types.SimpleNamespace(value="telegram"), chat_id="-1001111111111", chat_type="group")
session_entry = types.SimpleNamespace(session_id="20261016_test")

cases = [
    ("маркер молчания на адресованном", {"final_response": "[SILENT]", "api_calls": 1, "messages": []}, None),
    ("маркер молчания в личке", {"final_response": "  [SILENT]  ", "api_calls": 1, "messages": []}, None),
    ("служебное «что-то пошло не так»", {"final_response": t("gateway.errors.generic_failed"), "api_calls": 1, "messages": []}, None),
    ("пустой ответ модели", {"final_response": "", "api_calls": 2, "messages": []}, None),
]
for name, result, kind in cases:
    try:
        response, silent, _ = asyncio.run(GatewayTurnMixin._hmwa_shape_agent_response(
            stub, result, source, [], session_entry, "key", "quick", 1, "seed", "telegram", 0.0,
            persist_user_display_kind=kind, reply_expected=None))
        check(f"{name}: в чат ничего", response == "" and silent is True, f"response={response!r} silent={silent}")
    except Exception as exc:  # noqa: BLE001
        check(f"{name}: сборка хода не падает ({type(exc).__name__})", False, str(exc)[:140])

# 5. Живой ответ по-прежнему проходит
try:
    response, silent, _ = asyncio.run(GatewayTurnMixin._hmwa_shape_agent_response(
        stub, {"final_response": "да ну, с чего ты взял (￣ヘ￣)", "api_calls": 1, "messages": []},
        source, [], session_entry, "key", "quick", 1, "seed", "telegram", 0.0,
        persist_user_display_kind=None, reply_expected=True))
    check("живой ответ доходит", response == "да ну, с чего ты взял (￣ヘ￣)" and silent is False, f"{response!r}")
except Exception as exc:  # noqa: BLE001
    check(f"живой ответ: не падает ({type(exc).__name__})", False, str(exc)[:140])

print("\nSILENCE-SERVICE", "PASSED" if not fail else f"FAILED: {fail}")
sys.exit(1 if fail else 0)
