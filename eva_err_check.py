"""Проверка ветки ошибок Евы: сбой хода уходит в личку владельцу, а не в чат, где случился.

Поднимает настоящий BaseAdapter._notify_turn_error из форка на фейковом адаптере:
телеграм-либы и сеть не нужны, send() перехватывается.
"""
import asyncio
import os
import sys
import types

os.environ["HERMES_HOME"] = "/home/iizey/eva-home"
os.environ["HERMES_DISABLE_TELEGRAM"] = "1"
sys.path.insert(0, "/home/iizey/eva-hermes")

from gateway.platforms.base import BasePlatformAdapter as BaseAdapter  # noqa: E402

OWNER_DM = "111111111"
GROUP = "-1001111111111"
sent: list[tuple[str, str]] = []
fail: list[str] = []


class Fake(BaseAdapter):
    name = "Telegram"          # перекрывает property базового класса

    def __init__(self, extra):
        self.config = types.SimpleNamespace(extra=extra)
        self.platform = "telegram"

    async def connect(self):  # заглушки абстрактных методов
        return True

    async def disconnect(self):
        return None

    async def get_chat_info(self, chat_id):
        return {}

    async def send(self, chat_id, content, metadata=None, **kw):
        sent.append((str(chat_id), str(content)))

        class R:
            success = True
            message_id = None

        return R()


def ev(chat_id):
    return types.SimpleNamespace(
        source=types.SimpleNamespace(platform="telegram", chat_id=chat_id),
        internal=False, metadata={})


def expect(name, cond, extra=""):
    print(f"[{'ok' if cond else 'FAIL'}] {name}{' ' + str(extra) if extra else ''}")
    if not cond:
        fail.append(name)


async def main():
    a = Fake({"error_dm_chat_id": OWNER_DM})

    sent.clear()
    await BaseAdapter._notify_turn_error(a, ev(GROUP), RuntimeError("provider exploded"))
    targets = [c for c, _ in sent]
    expect("сбой в группе -> ровно одно сообщение", len(sent) == 1, sent)
    expect("...и оно ушло в личку владельца", targets == [OWNER_DM], targets)
    expect("...в группе не осталось ничего", GROUP not in targets, targets)
    expect("...в личке есть текст ошибки",
           "provider exploded" in sent[0][1] and "RuntimeError" in sent[0][1], sent[0][1][:160])
    expect("...и понятно, откуда сбой", GROUP in sent[0][1], sent[0][1][:80])

    sent.clear()
    await BaseAdapter._notify_turn_error(a, ev(OWNER_DM), ValueError("boom"))
    expect("сбой в личке владельца -> тоже в личку, с деталями",
           len(sent) == 1 and sent[0][0] == OWNER_DM and "boom" in sent[0][1], sent)

    sent.clear()
    b = Fake({})  # без настройки — поведение апстрима (сообщение в исходный чат)
    os.environ.pop("HERMES_ERROR_DM_CHAT_ID", None)
    try:
        await BaseAdapter._notify_turn_error(b, ev(GROUP), ValueError("plain"))
    except Exception as exc:  # noqa: BLE001 — апстрим-ветка в фейке может упасть глубже
        print("  (апстрим-ветка в фейке: %s)" % type(exc).__name__)
    expect("без error_dm_chat_id личка не выдумывается",
           all(c != OWNER_DM for c, _ in sent), sent)

    print("ERROR-ROUTING", "PASSED" if not fail else f"FAILED: {fail}")
    return 1 if fail else 0


sys.exit(asyncio.run(main()))
