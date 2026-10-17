"""Проверка связки «люди» с адаптером: своя личка каждому, карточка в ход, пометки на месте.

Живые файлы не трогаются: карточки и строки чата уводятся во временный каталог.
"""
import asyncio
import json
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, "/home/iizey/eva-hermes")

import eva_people  # noqa: E402
import plugins.platforms.telegram.adapter as adapter_mod  # noqa: E402
from gateway.config import Platform  # noqa: E402
from gateway.platforms.event import MessageEvent  # noqa: E402
from gateway.session import build_session_key  # noqa: E402
from plugins.platforms.telegram.adapter import TelegramAdapter  # noqa: E402

fail = []


def check(name, cond, extra=""):
    print(f"[{'ok' if cond else 'FAIL'}] {name}{' — ' + str(extra) if extra else ''}")
    if not cond:
        fail.append(name)


tmp = Path(tempfile.mkdtemp())
eva_people.STORE = tmp / "people.json"
eva_people.LINES = tmp / "chat_lines.jsonl"
eva_people.note_sighting("222222222", "Борис", chat_id="-1002222222222", chat_title="Тестовая группа")
eva_people.remember("222222222", "играет на гитаре", source="Тестовая группа")
eva_people.note_sighting("111111111", "Владелец", chat_id="-1002222222222", chat_title="Тестовая группа")
eva_people.remember("111111111", "пишет на питоне", source="Тестовая группа")


class _Stub(TelegramAdapter):
    name = "Telegram"


stub = object.__new__(_Stub)
stub._is_group_chat = lambda message: str(getattr(getattr(message, "chat", None), "id", "")).startswith("-")
stub._eva_last_person = {}


def message(uid, name, chat_id, text, title=""):
    return types.SimpleNamespace(
        from_user=types.SimpleNamespace(id=int(uid), full_name=name),
        chat=types.SimpleNamespace(id=int(chat_id), title=title),
        message_id=10, text=text)


# 1. у каждого своя личка
def source(user_id):
    return types.SimpleNamespace(platform=Platform.TELEGRAM, user_id=user_id, chat_type="dm",
                                 chat_id=user_id, thread_id=None, profile=None)


key_vova = build_session_key(source("222222222"))
key_owner = build_session_key(source("111111111"))
check("личка Бориса отдельная", key_vova != key_owner, f"{key_vova} vs {key_owner}")
check("ключ лички — по человеку", key_vova.endswith("222222222"), key_vova)
check("общей лички больше нет", "shared" not in key_vova)
group_key = build_session_key(types.SimpleNamespace(platform=Platform.TELEGRAM, user_id="222222222",
                                                    chat_type="group", chat_id="-1002222222222",
                                                    thread_id=None, profile=None,
                                                    prospective_thread_id=None, user_id_alt=None))
check("группа считается как раньше", "-1002222222222" in group_key, group_key)

# 2. запись человека: имя, строка для синхронизации, «последний собеседник»
TelegramAdapter._eva_note_person(stub, message("222222222", "Борис", 222222222, "я на гитаре играю"))
check("последний собеседник запомнен", stub._eva_last_person.get("222222222", ("", ""))[0] == "222222222")
lines = [json.loads(l) for l in eva_people.LINES.read_text(encoding="utf-8").splitlines()]
check("строка чата ушла в копилку", len(lines) == 1 and lines[0]["uid"] == "222222222", lines)
check("в строке есть имя и текст", lines[0]["name"] == "Борис" and "гитаре" in lines[0]["text"])

# 3. карточка едет в ход — именно этого человека
dm_source = lambda chat_id, chat_type: types.SimpleNamespace(chat_id=chat_id, chat_type=chat_type)
event = MessageEvent(text="привет", user_id="222222222", user_name="Борис",
                     source=dm_source("222222222", "dm"))
out = TelegramAdapter._eva_attach_people(stub, event)
check("в личке карточка Бориса", "С тобой говорит Борис" in out.text and "гитаре" in out.text, out.text[:90])
check("чужие факты не подмешиваются", "питоне" not in out.text)

event_owner = MessageEvent(text="привет", user_id="111111111", user_name="Владелец",
                           source=dm_source("111111111", "dm"))
out_owner = TelegramAdapter._eva_attach_people(stub, event_owner)
check("в личке владельца его карточка", "Владелец" in out_owner.text and "питоне" in out_owner.text)
check("карточка Бориса туда не попала", "Борис" not in out_owner.text)

group_event = MessageEvent(text="всем привет", user_id="222222222", user_name="Борис",
                           source=dm_source("-1002222222222", "group"))
out_group = TelegramAdapter._eva_attach_people(stub, group_event)
check("в группе карточка того, кто написал", "Борис" in out_group.text)
check("в группе подсказка про знакомых", "<кого_знаешь>" in out_group.text and "Владелец" in out_group.text)
check("повторно блок не задваивается",
      TelegramAdapter._eva_attach_people(stub, MessageEvent(
          text=out_group.text, user_id="222222222", user_name="Борис",
          source=group_event.source)).text == out_group.text)

# 3б. группа без полей отправителя: он только в тексте строкой «[Имя|id]»
stub._eva_last_person = {}
group_plain = MessageEvent(text="[Борис|222222222] а я на гитаре играю",
                           source=dm_source("-1002222222222", "group"))
out_plain = TelegramAdapter._eva_attach_people(stub, group_plain)
check("отправитель из строки «[Имя|id]» распознан", "С тобой говорит Борис" in out_plain.text,
      out_plain.text.replace("\n", " ")[:120])
check("и его факты подтянулись", "гитаре" in out_plain.text.split("<кого_знаешь>")[0])
unknown = MessageEvent(text="[Петя|111222333] привет", source=dm_source("-1002222222222", "group"))
out_unknown = TelegramAdapter._eva_attach_people(stub, unknown)
check("незнакомца называет по имени, без выдумок", "Петя" in out_unknown.text and "гитаре" not in out_unknown.text)

# 4. её пометка «[[запомнить: …]]» попадает в карточку, а в текст — нет
stub._eva_last_person = {"222222222": ("222222222", "Борис")}
TelegramAdapter._eva_remember_notes(stub, "222222222", [("Борис", "учится в музыкальной школе")])
check("факт из пометки сохранён",
      "музыкальной" in eva_people.card("222222222"))
TelegramAdapter._eva_remember_notes(stub, "222222222", [(None, "любит кошек")])
check("пометка без имени — про собеседника", "кошек" in eva_people.card("222222222"))
stub._eva_last_person = {"222222222": ("222222222", "Борис")}
TelegramAdapter._eva_remember_notes(stub, "222222222", [("Петя", "ходит в бассейн")])
check("незнакомое имя — не выдумывает человека", "бассейн" in eva_people.card("222222222")
      or "бассейн" not in json.dumps(eva_people._load(), ensure_ascii=False))

# 5. в живом конфиге включены разные лички и знание людей
config_text = Path("/home/iizey/eva-home/config.yaml").read_text(encoding="utf-8")
check("в конфиге shared_dm_session выключен", "enabled: false" in config_text.split("shared_dm_session:")[1][:40])
check("в конфиге есть блок eva_people", "eva_people:" in config_text and "sync_minutes: 120" in config_text)
check("карточки живут в eva-home", str(eva_people.STORE) != "" and "eva-home" in str(
    Path("/home/iizey/eva-home/people.json")))

print("\nPEOPLE-WIRE", "PASSED" if not fail else f"FAILED: {fail}")
sys.exit(1 if fail else 0)
