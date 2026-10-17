"""Проверка реакций: набор Telegram, подтверждения рубильника, маркер «[[реакция: …]]»."""
import asyncio
import sys
import types

sys.path.insert(0, "/home/iizey/eva-hermes")

import plugins.platforms.telegram.adapter as adapter_mod  # noqa: E402
from plugins.platforms.telegram.adapter import TelegramAdapter, _eva_normalize_reaction  # noqa: E402

fail = []


def check(name, cond, extra=""):
    print(f"[{'ok' if cond else 'FAIL'}] {name}{' — ' + str(extra) if extra else ''}")
    if not cond:
        fail.append(name)


# 1. Набор, который Telegram реально принимает
for emoji in ["🔥", "👍", "🙊", "👀", "❤️", "😭", "🎉", "💯", "🤔", "😴"]:
    check(f"принимается: {emoji}", _eva_normalize_reaction(emoji) == emoji, _eva_normalize_reaction(emoji))

# 2. То, на чём сломалось подтверждение рубильника, и прочие неподдерживаемые
for emoji in ["🔇", "🤐", "🤫", "▶️"]:   # подменяются на рабочие — но не уходят как есть
    check(f"как есть не отправляется: {emoji!r}", _eva_normalize_reaction(emoji) != emoji,
          _eva_normalize_reaction(emoji))
for emoji in ["🍕", "🚀", ""]:           # совсем не поддерживаются
    check(f"не поддерживается: {emoji!r}", adapter_mod._eva_reaction_allowed(emoji) is False,
          _eva_normalize_reaction(emoji))

# 3. Частые промахи подменяются на поддерживаемые
for raw, want in [("🤐", "🙊"), ("🔇", "🙊"), ("▶️", "👀"), ("🐱", "❤️"), ("😂", "🤣"), ("😊", "😁")]:
    check(f"подмена {raw} → {want}", _eva_normalize_reaction(raw) == want, _eva_normalize_reaction(raw))


class Bot:
    def __init__(self):
        self.calls = []

    async def set_message_reaction(self, **kwargs):
        self.calls.append(kwargs)
        return True


class _Stub(TelegramAdapter):
    name = "Telegram"


stub = object.__new__(_Stub)
stub._bot = Bot()
stub._eva_recent = {}
stub._eva_muted_cache = None
stub._is_group_chat = lambda message: False

# 4. Подтверждение рубильника ставится поддерживаемым эмодзи
msg = types.SimpleNamespace(chat=types.SimpleNamespace(id=-1001111111111), message_id=99)
ok_stop = asyncio.run(TelegramAdapter._eva_control_react(stub, msg, "🙊"))
ok_alias = asyncio.run(TelegramAdapter._eva_control_react(stub, msg, "🔇"))
ok_bad = asyncio.run(TelegramAdapter._eva_control_react(stub, msg, "🍕"))
check("подтверждение «заткнута» ставится", ok_stop is True and stub._bot.calls[-1]["reaction"] == "🙊",
      stub._bot.calls[-1] if stub._bot.calls else None)
check("запрещённый эмодзи подменяется рабочим", ok_alias is True and stub._bot.calls[-1]["reaction"] == "🙊",
      stub._bot.calls[-1])
check("неподдерживаемый эмодзи не отправляется вовсе", ok_bad is False)
check("в Bot API не ушло ничего лишнего", all(c["reaction"] in adapter_mod._EVA_REACTION_EMOJI for c in stub._bot.calls),
      stub._bot.calls)

# 5. Маркер реакции в её сообщении
clean, emoji = TelegramAdapter._eva_split_reaction_marker(stub, "[[реакция: 🔥]]")
check("только маркер → пустой текст + эмодзи", (clean, emoji) == ("", "🔥"), (clean, emoji))
clean, emoji = TelegramAdapter._eva_split_reaction_marker(stub, "[[реакция: 🔥]] ну ты выдал")
check("маркер + текст", (clean, emoji) == ("ну ты выдал", "🔥"), (clean, emoji))
clean, emoji = TelegramAdapter._eva_split_reaction_marker(stub, "[[реакция: 🍕]] привет")
check("неподдерживаемый эмодзи: маркер снят, текст цел", (clean, emoji) == ("привет", ""), (clean, emoji))
clean, emoji = TelegramAdapter._eva_split_reaction_marker(stub, "обычный текст")
check("без маркера ничего не меняется", (clean, emoji) == ("обычный текст", ""), (clean, emoji))

# 6. Реакция ставится на сообщение собеседника, а не её собственное, и текста не отправляет
adapter_mod.normalize_telegram_chat_id = lambda value: value
stub._eva_last_inbound = {"-1001111111111": "4242"}
stub._eva_apply_topic_marker = lambda chat_id, content, metadata: (content, metadata)
stub._eva_resolve_sticker_marker = lambda content: (content, None)
stub._eva_style = lambda content: content
stub._eva_meta_blocked = lambda content: False
stub._eva_note_own_message = lambda chat_id, content: None
stub._eva_muted = lambda: False   # иначе рубильник съест отправку (он сейчас может быть включён)
stub._bot.calls.clear()
sent_text = []


def _no_text(*args, **kwargs):
    raise AssertionError("текст не должен отправляться, если ответ — одна реакция")


stub._send_text_locked = _no_text
import types as _types  # noqa: E402

asyncio.run(TelegramAdapter.send(stub, "-1001111111111", "[[реакция: 👍]]"))
check("реакция ушла на сообщение собеседника", stub._bot.calls and stub._bot.calls[-1]["message_id"] == 4242,
      stub._bot.calls[-1] if stub._bot.calls else None)
check("чат верный", stub._bot.calls[-1]["chat_id"] == "-1001111111111", stub._bot.calls[-1])

# 7. Если нечего реагировать (нет входящего) — тихо ничего не делаем
stub._eva_last_inbound = {}
ok = asyncio.run(TelegramAdapter._eva_react_to_last(stub, "-1001111111111", "🔥"))
check("без входящего сообщения реакция не падает", ok is False)

# 8. Блок реакций есть в промте и перечисляет поддерживаемые эмодзи
block = TelegramAdapter._eva_reaction_prompt(stub)
check("в промте объяснён маркер", "[[реакция:" in block)
check("в промте перечислены рабочие эмодзи", "🔥" in block and "🙊" in block and "🔇" not in block)

# 9. Фильтр сам решил, что хватит смайлика: реакция ставится, ход не открывается
async def _tick(seconds=0.05):
    await asyncio.sleep(seconds)


stub.config = types.SimpleNamespace(extra={"eva_reaction_cooldown_seconds": 0})
stub._eva_reaction_at = {}
stub._bot.calls.clear()
observed, turns = [], []


def _gate_classify(msg, merged=None):
    return "react", "🤣"


stub._eva_gate_classify = _gate_classify
stub._should_process_message = lambda msg: False
stub._should_observe_unmentioned_group_message = lambda msg: True
stub._eva_remember_group_line = lambda msg: None
stub._observe_unmentioned_group_message = lambda msg, msg_type, update_id=None: observed.append(msg.text)
fake_message = types.SimpleNamespace(chat=types.SimpleNamespace(id=-1001111111111), message_id=777,
                                   from_user=types.SimpleNamespace(id=1, full_name="Паша"), text="ахахах мем")
async def _run_gate():
    result = TelegramAdapter._gate_or_observe(stub, fake_message, types.SimpleNamespace(update_id=1), "text")
    await asyncio.sleep(0.05)          # даём задаче реакции выполниться
    return result


proceed = asyncio.run(_run_gate())
check("вердикт «реакция» не открывает ход", proceed is False, proceed)
check("смайлик при этом поставлен", stub._bot.calls and stub._bot.calls[-1]["reaction"] == "🤣",
      stub._bot.calls[-1] if stub._bot.calls else None)
check("сообщение попало в наблюдение", observed == ["ахахах мем"], observed)

# 10. Пауза между автореакциями, чтобы не частить
stub.config.extra["eva_reaction_cooldown_seconds"] = 60
stub._eva_reaction_at = {}
stub._bot.calls.clear()
async def _react_twice():
    TelegramAdapter._eva_react_to_message(stub, fake_message, "🔥")
    await asyncio.sleep(0.05)
    first_calls = len(stub._bot.calls)
    TelegramAdapter._eva_react_to_message(stub, fake_message, "🔥")
    await asyncio.sleep(0.05)
    return first_calls


first = asyncio.run(_react_twice())
check("первая автореакция уходит", first == 1, first)
check("вторая подряд — нет (пауза на чат)", len(stub._bot.calls) == 1, len(stub._bot.calls))

# 11. Вердикт «ответить» — ход открывается как раньше
stub._eva_gate_classify = lambda msg, merged=None: ("reply", "")
proceed = TelegramAdapter._gate_or_observe(stub, fake_message, types.SimpleNamespace(update_id=1), "text")
check("вердикт «ответить» открывает ход", proceed is True, proceed)

print("\nREACTIONS", "PASSED" if not fail else f"FAILED: {fail}")
sys.exit(1 if fail else 0)
