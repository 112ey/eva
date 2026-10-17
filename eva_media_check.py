"""Проверка медиа-пути: фото с «посмотри» доходит до неё, фильтр видит пометку «(фото)»."""
import os
import sys
import types

os.environ.setdefault("HERMES_HOME", "/home/iizey/eva-home")
sys.path.insert(0, "/home/iizey/eva-hermes")

from plugins.platforms.telegram.adapter import TelegramAdapter  # noqa: E402

fail = []


def check(name, cond, extra=""):
    print(f"[{'ok' if cond else 'FAIL'}] {name}{' — ' + str(extra) if extra else ''}")
    if not cond:
        fail.append(name)


def msg(**kw):
    base = dict(text=None, caption=None, photo=None, video=None, sticker=None,
                from_user=types.SimpleNamespace(full_name="Владелец"),
                chat=types.SimpleNamespace(id=-1001111111111, type="supergroup"),
                message_thread_id=None)
    base.update(kw)
    return types.SimpleNamespace(**base)


class Stub(TelegramAdapter):
    name = "Telegram"

    def __init__(self, group=True):
        self.group = group
        self._eva_recent = {}
        self._eva_seeded = set()

    def _is_group_chat(self, message):
        return self.group

    def _chat_id_str(self, message):
        return str(message.chat.id)

    def _eva_seed_gate_lines(self, chat_id, message):
        return None


stub = Stub()

# 1. Когда фото «зовёт посмотреть» — отвечаем без фильтра
check("фото + «Смотрите какой кошак»",
      TelegramAdapter._eva_media_wants_attention(stub, msg(photo=[1], caption="Смотрите какой кошак")) is True)
check("фото + «Как тебе?»",
      TelegramAdapter._eva_media_wants_attention(stub, msg(photo=[1], caption="Как тебе?")) is True)
check("стикер + «оцени»",
      TelegramAdapter._eva_media_wants_attention(stub, msg(sticker=object(), caption="оцени")) is True)
check("фото без подписи — не обращение",
      TelegramAdapter._eva_media_wants_attention(stub, msg(photo=[1])) is False)
check("фото с чужой подписью — не обращение",
      TelegramAdapter._eva_media_wants_attention(stub, msg(photo=[1], caption="моя новая тачка")) is False)
check("просто текст «посмотри» — не медиа-путь",
      TelegramAdapter._eva_media_wants_attention(stub, msg(text="посмотри")) is False)
check("в личке медиа-правило не работает",
      TelegramAdapter._eva_media_wants_attention(Stub(group=False), msg(photo=[1], caption="смотри")) is False)

# 2. Фильтр видит, что прислали картинку
TelegramAdapter._eva_remember_group_line(stub, msg(photo=[1], caption="Смотрите какой кошак"))
TelegramAdapter._eva_remember_group_line(stub, msg(photo=[1]))
TelegramAdapter._eva_remember_group_line(stub, msg(text="кто видел зарядник?"))
window = stub._eva_recent["-1001111111111"]
check("подпись с фото помечена", window[0] == "[Владелец] (фото) Смотрите какой кошак", window[0])
check("фото без подписи помечено", window[1] == "[Владелец] (фото)", window[1])
check("обычный текст без пометки", window[2] == "[Владелец] кто видел зарядник?", window[2])

# 3. Живой фильтр на этих строках
from plugins.platforms.telegram.eva_gate import should_reply  # noqa: E402
history = ["[Паша] вот мем", "[Максим] ахахах"]
verdict_photo = should_reply(history + ["[Владелец] (фото) Смотрите какой кошак"], "[Владелец] (фото) Смотрите какой кошак")
verdict_chat = should_reply(history, "[Паша] ну и ладно")
check("фильтр зовёт её на фото с просьбой", verdict_photo is not False, verdict_photo)
check("фильтр по-прежнему молчит на болтовне", verdict_chat is False, verdict_chat)

print("\nMEDIA", "PASSED" if not fail else f"FAILED: {fail}")
sys.exit(1 if fail else 0)
