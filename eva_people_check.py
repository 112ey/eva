"""Проверка карточек людей: запоминание, дедуп, карточка для промта, пометки, синхронизация."""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/home/iizey/eva-hermes")

import eva_people  # noqa: E402
import people_sync  # noqa: E402

fail = []


def check(name, cond, extra=""):
    print(f"[{'ok' if cond else 'FAIL'}] {name}{' — ' + str(extra) if extra else ''}")
    if not cond:
        fail.append(name)


tmp = Path(tempfile.mkdtemp())
eva_people.STORE = tmp / "people.json"
eva_people.LINES = tmp / "chat_lines.jsonl"
people_sync.STATE = tmp / "people_sync_state.json"
people_sync.HOME = tmp

# 1. имя, факты, дедуп
eva_people.note_sighting("222222222", "Борис", chat_id="-1002222222222", chat_title="Тестовая группа")
check("имя записано", (eva_people._load()["people"]["222222222"]["name"] == "Борис"))
check("факт принят", eva_people.remember("222222222", "играет на гитаре", source="Тестовая группа") is True)
check("тот же факт второй раз не дублируется",
      eva_people.remember("222222222", "играет на гитаре") is False)
check("факт внутри другого факта тоже не дублируется",
      eva_people.remember("222222222", "играет на гитаре и поёт") is False)
check("новый факт принимается", eva_people.remember("222222222", "есть кот Барсик") is True)

# 2. карточка
card = eva_people.card("222222222")
check("карточка называет человека", "Борис" in card, card.splitlines()[1] if card else "")
check("карточка содержит факты", "гитаре" in card and "Барсик" in card)
check("карточка не велит пересказывать справку", "не пересказывай" in card)
check("чужой человек — пустая карточка", eva_people.card("999") == "")

# 3. поиск по имени и группы
check("ищет по имени", eva_people.find_by_name("Борис") == ["222222222"])
check("ищет по прозвищу", eva_people.find_by_name("Борька") == ["222222222"])
check("незнакомое имя не находит", eva_people.find_by_name("Петя") == [])
check("подсказка про знакомых в чате", "Борис" in eva_people.known_here("-1002222222222"))
check("в чужом чате знакомых нет", eva_people.known_here("-1000000000") == "")

# 4. пометки из её ответа
cleaned, notes = eva_people.split_marker("ага, привет :) [[запомнить: Борис — играет на гитаре]]")
check("пометка с именем разобрана", notes == [("Борис", "играет на гитаре")], notes)
check("маркер вырезан из текста", cleaned == "ага, привет :)", cleaned)
cleaned, notes = eva_people.split_marker("ок [[запомнить: есть кот]]")
check("пометка без имени — про собеседника", notes == [(None, "есть кот")], notes)
cleaned, notes = eva_people.split_marker("ок [[запомнить: Борис: ходит в музыкалку]]")
check("двоеточие тоже годится", notes == [("Борис", "ходит в музыкалку")], notes)
cleaned, notes = eva_people.split_marker("совсем без пометок")
check("без пометок текст не тронут", (cleaned, notes) == ("совсем без пометок", []), (cleaned, notes))

# 5. строки чата и синхронизация
eva_people.log_line("222222222", "Борис", "я вообще-то на гитаре играю", chat_id="-1002222222222",
                    chat_title="Тестовая группа")
eva_people.log_line("111111111", "Владелец", "а я в террарию опять залип", chat_id="-1002222222222",
                    chat_title="Тестовая группа")
rows, offset = people_sync._read_new_lines(0)
check("строки чата читаются все", len(rows) == 2, len(rows))
rows2, offset2 = people_sync._read_new_lines(offset)
check("повторно те же строки не читаются", rows2 == [], rows2)
check("окно отсекает старое", len([r for r in rows if r["ts"] >= 1]) == 2)

# 6. слияние фактов из синхронизации (модель подменена)
person = eva_people._load()["people"]["222222222"]
before = len(person["facts"])
eva_people.remember("222222222", "учится в музыкальной школе", source="Тестовая группа")
after = eva_people._load()["people"]["222222222"]["facts"]
check("синхронизация добавляет факт", len(after) == before + 1)
check("факты не теряют источник", any(f.get("source") == "Тестовая группа" for f in after))
check("карточка обновилась", "музыкальной" in eva_people.card("222222222"))

# 7. потолок фактов — карточка не разрастается бесконечно
for index in range(60):
    eva_people.remember("222222222", f"случайный факт номер {index}")
facts = eva_people._load()["people"]["222222222"]["facts"]
check("факты ограничены потолком", len(facts) <= eva_people.MAX_FACTS, len(facts))
check("в карточку идёт не всё", eva_people.card("222222222").count(";") <= 12)

print("\nPEOPLE", "PASSED" if not fail else f"FAILED: {fail}")
sys.exit(1 if fail else 0)
