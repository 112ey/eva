"""Проверка: Ева читает названия тем и понимает, куда писать."""
import os
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, "/home/iizey/eva-hermes")
sys.path.insert(0, "/home/iizey/eva-home")

import eva_topics  # noqa: E402

fail = []
CHAT = "-1002222222222"


def check(name, cond, extra=""):
    print(f"[{'ok' if cond else 'FAIL'}] {name}{' — ' + str(extra) if extra else ''}")
    if not cond:
        fail.append(name)


tmp = Path(tempfile.mkdtemp()) / "topics.json"
eva_topics.TOPICS_FILE = tmp
eva_topics.HOME = tmp.parent

# 1. Имена тем собираются из сообщений
eva_topics.record(CHAT, 1, "General")
eva_topics.record(CHAT, 12, "Мемы и коты")
eva_topics.record(CHAT, 27, "Кино и сериалы")
eva_topics.record(CHAT, 12, "Мемы и коты")          # та же тема, повтор
eva_topics.record(CHAT, 40, "   ")                   # пустое имя — мимо
check("три темы записаны", len(eva_topics.topics(CHAT)) == 3, eva_topics.topics(CHAT))
check("пустое имя не пишется", "40" not in eva_topics.topics(CHAT))

# 2. Она видит их в промте, с пометкой текущей
block = eva_topics.prompt_block(CHAT, current_thread="12")
check("блок тем собран", "Мемы и коты" in block and "Кино и сериалы" in block)
check("видно, где она сейчас", "← ты сейчас тут" in block and "Мемы и коты (id 12)  ←" in block)
check("одна тема — блока нет", eva_topics.prompt_block("-1009999999999") == "")

# 3. Понимает, куда писать: маркер
name, cleaned = eva_topics.parse_marker("[[тема: Кино и сериалы]] посмотрела новый трейлер")
check("маркер разобран", name == "Кино и сериалы", name)
check("маркер убран из текста", cleaned == "посмотрела новый трейлер", cleaned)
check("без маркера текст не тронут", eva_topics.parse_marker("привет") == (None, "привет"))
check("маркер с пробелами/регистром", eva_topics.parse_marker("[[ Тема : мемы и коты ]] кошак")[0].lower() == "мемы и коты")
check("тема по точному имени", eva_topics.resolve(CHAT, "Кино и сериалы") == "27")
check("тема по id", eva_topics.resolve(CHAT, "12") == "12")
check("тема по куску названия", eva_topics.resolve(CHAT, "мемы") == "12")
check("несуществующая тема", eva_topics.resolve(CHAT, "политика") is None)

# 4. Сама выбирает тему по смыслу (для её сообщений по таймеру)
check("про мемы → Мемы и коты", eva_topics.best_thread(CHAT, "нашла новый мем, ору") == "12",
      eva_topics.best_thread(CHAT, "нашла новый мем, ору"))
check("без общих слов — тема не навязана", eva_topics.best_thread(CHAT, "видела кошака во дворе") is None,
      eva_topics.best_thread(CHAT, "видела кошака во дворе"))
check("про сериал → Кино и сериалы", eva_topics.best_thread(CHAT, "сериал вчера досмотрела, финал так себе") == "27",
      eva_topics.best_thread(CHAT, "сериал вчера досмотрела, финал так себе"))
check("ничего не подошло → General", eva_topics.best_thread(CHAT, "привет, как дела") is None)
check("General не предлагается как тема", "1" not in [eva_topics.best_thread(CHAT, t) for t in ("general", "общее")])

# 5. Отправка: маркер превращается в thread_id
sys.path.insert(0, "/home/iizey/eva-home")
import send_local  # noqa: E402

send_local.__dict__.setdefault("HOME", send_local.HOME)
text, tid = send_local.pick_thread(CHAT, "[[тема: Мемы и коты]] вот мем", True)
check("отправка: маркер → thread_id", (tid, text) == ("12", "вот мем"), (tid, text))
text, tid = send_local.pick_thread(CHAT, "сериал вчера досмотрела", True)
check("отправка: выбор темы по смыслу", tid == "27", tid)
text, tid = send_local.pick_thread(CHAT, "сериал вчера досмотрела", False)
check("без флага тема не выбирается", tid == "", tid)

# 6. Адаптер: маркер подменяет metadata отправки
from plugins.platforms.telegram.adapter import TelegramAdapter  # noqa: E402


class _Stub(TelegramAdapter):
    name = "Telegram"   # перекрывает property базового класса


stub = object.__new__(_Stub)
content, meta = TelegramAdapter._eva_apply_topic_marker(stub, CHAT, "[[тема: Кино]] привет", {"thread_id": "1"})
check("адаптер: metadata получила тему", (content, meta) == ("привет", {"thread_id": "27"}), (content, meta))
content, meta = TelegramAdapter._eva_apply_topic_marker(stub, CHAT, "[[тема: политика]] привет", {"thread_id": "1"})
check("адаптер: неизвестная тема — маркер снят, ветка прежняя",
      (content, meta.get("thread_id")) == ("привет", "1"), (content, meta))
content, meta = TelegramAdapter._eva_apply_topic_marker(stub, CHAT, "обычный ответ", None)
check("адаптер: без маркера ничего не меняется", (content, meta) == ("обычный ответ", None))

# 7. Имя темы из сообщения Telegram
msg = types.SimpleNamespace(message_thread_id=27,
                            forum_topic_created=None,
                            reply_to_message=types.SimpleNamespace(forum_topic_created=types.SimpleNamespace(name="Кино и сериалы")))
TelegramAdapter._eva_remember_topic(stub, CHAT, msg)
check("тема из ответа в ветке записана", eva_topics.topics(CHAT).get("27") == "Кино и сериалы")

# 8. Имя текущей темы видно и без списка (одна известная ветка — уже полезно)
eva_topics.TOPICS_FILE = tmp.parent / "solo.json"
eva_topics.record(CHAT, 9245, "Скинь дз")
check("одна тема — блок всё равно есть", "Скинь дз" in eva_topics.prompt_block(CHAT, "9245"))
check("имя темы по id для промта", eva_topics.name_of(CHAT, "9245") == "Скинь дз")
check("неизвестный id — имени нет", eva_topics.name_of(CHAT, "777") is None)
check("личка/не-форум — имени нет", eva_topics.name_of("-100999", "1") is None)

# 9. Имя темы из сервисного апдейта (создание и переименование)
def upd(**kw):
    return types.SimpleNamespace(**kw)


service = upd(message=types.SimpleNamespace(
    chat=types.SimpleNamespace(id=CHAT), message_thread_id=555,
    forum_topic_created=types.SimpleNamespace(name="Новая тема"),
    forum_topic_edited=None, reply_to_message=None))
TelegramAdapter._eva_record_topic_from_update(stub, service)
check("тема из сервисного сообщения о создании", eva_topics.topics(CHAT).get("555") == "Новая тема")

renamed = upd(message=types.SimpleNamespace(
    chat=types.SimpleNamespace(id=CHAT), message_thread_id=555,
    forum_topic_created=None,
    forum_topic_edited=types.SimpleNamespace(name="Переименованная"),
    reply_to_message=None))
TelegramAdapter._eva_record_topic_from_update(stub, renamed)
check("переименование темы подхвачено", eva_topics.topics(CHAT).get("555") == "Переименованная")

reply_topic = upd(message=types.SimpleNamespace(
    chat=types.SimpleNamespace(id=CHAT), message_thread_id=556,
    forum_topic_created=None, forum_topic_edited=None,
    reply_to_message=types.SimpleNamespace(forum_topic_created=types.SimpleNamespace(name="Кино и сериалы"))))
TelegramAdapter._eva_record_topic_from_update(stub, reply_topic)
check("тема из обычного сообщения в ветке", eva_topics.topics(CHAT).get("556") == "Кино и сериалы")

TelegramAdapter._eva_record_topic_from_update(stub, upd(callback_query=object()))
check("апдейт без сообщения не ломает учёт", True)

# 10. Сквозная сборка события: тема попадает и в источник (Channel Topic), и в блок промта
from gateway.session import Platform  # noqa: E402


class _Ev(TelegramAdapter):
    name = "Telegram"
    platform = Platform.TELEGRAM

    def __init__(self):
        self.config = types.SimpleNamespace(extra={})

    def _effective_message_thread_id(self, message):
        return "9245"

    def _resolve_topic_binding(self, message, chat_type, thread_id_str):
        return None, None


ev = object.__new__(_Ev)
_Ev.__init__(ev)
raw = types.SimpleNamespace(
    chat=types.SimpleNamespace(id=-1002222222222, title="Тестовая группа", type="supergroup"),
    from_user=types.SimpleNamespace(id=111111111, full_name="Владелец", is_bot=False),
    message_id=42, message_thread_id=9245, date=None, is_topic_message=True,
    text="Ева, в какой мы теме?", caption=None, forum_topic_created=None, quote=None,
    reply_to_message=types.SimpleNamespace(message_id=40, text=None, caption=None,
                                           forum_topic_created=types.SimpleNamespace(name="Скинь дз")))
try:
    event = TelegramAdapter._build_message_event(ev, raw, "text", None)
    check("тема в источнике события (Channel Topic)", event.source.chat_topic == "Скинь дз", event.source.chat_topic)
    check("блок тем в промте хода", "## Темы" in (event.channel_prompt or ""))
except Exception as exc:  # noqa: BLE001
    check(f"сборка события не падает ({type(exc).__name__})", False, str(exc)[:120])

print("\nTOPICS", "PASSED" if not fail else f"FAILED: {fail}")
sys.exit(1 if fail else 0)
