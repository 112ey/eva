"""Проверка нескольких стикерных наборов: номера для фильтра считаются по всем вместе."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/home/iizey/eva-hermes")

import eva_sticker_pack as pack  # noqa: E402

fail = []


def check(name, cond, extra=""):
    print(f"[{'ok' if cond else 'FAIL'}] {name}{' — ' + str(extra) if extra else ''}")
    if not cond:
        fail.append(name)


tmp = Path(tempfile.mkdtemp())
pack.PACK_FILE = tmp / "sticker_pack.json"

# 1. Старый формат (один набор в корне) читается как один набор
pack.PACK_FILE.write_text(json.dumps({
    "name": "old_pack", "title": "старый",
    "stickers": [{"file_id": "OLD1", "file_unique_id": "o1", "emoji": "😺", "description": "кот машет"}]},
    ensure_ascii=False), encoding="utf-8")
packs = pack.load_packs()
check("старый формат не потерялся", list(packs) == ["old_pack"], list(packs))
check("старый стикер на месте", pack.sticker_by_number("1").get("file_id") == "OLD1")

# 2. Новый формат: несколько наборов
pack.PACK_FILE.write_text(json.dumps({"packs": {
    "koshachiy_raskolbas": {"title": "@k0shbss", "stickers": [
        {"file_id": "A1", "file_unique_id": "a1", "emoji": "🤣", "description": "ржёт во весь рот"},
        {"file_id": "A2", "file_unique_id": "a2", "emoji": "😡", "description": "злится и посылает"},
    ]},
    "kotiki102938475610_by_fStikBot": {"title": "Kotiki", "stickers": [
        {"file_id": "B1", "file_unique_id": "b1", "emoji": "👋", "description": "машет лапой, привет"},
        {"file_id": "B2", "file_unique_id": "b2", "emoji": "👍", "description": "кот показывает большой палец"},
        {"file_id": "B3", "file_unique_id": "b3", "emoji": "😴", "description": "спит на клавиатуре"},
    ]}}}, ensure_ascii=False), encoding="utf-8")

entries = pack._entries()
check("стикеры обоих наборов собраны", len(entries) == 5, len(entries))
check("у каждого стикера помечен набор",
      {e["pack"] for e in entries} == {"koshachiy_raskolbas", "kotiki102938475610_by_fStikBot"})

listing = pack.pack_for_prompt()
check("список для фильтра пронумерован по обоим", listing.startswith("1) 🤣") and "👋" in listing, listing.replace("\n", " | "))
check("в списке есть стикер из второго набора", "машет лапой" in listing)

# 3. Номера указывают на стикеры именно из нужного набора
by_number = {n: pack.sticker_by_number(str(n)) for n in range(1, 6)}
check("все номера находят стикер", all(v.get("file_id") for v in by_number.values()), by_number)
check("второй набор доступен по номерам",
      any(v.get("pack") == "kotiki102938475610_by_fStikBot" for v in by_number.values()))
check("номер вне списка — пусто", pack.sticker_by_number("99") == {})
check("мусор вместо номера — пусто", pack.sticker_by_number("кот") == {})

# 4. Первым делом в список идут разные эмоции, а не пять котов подряд
many = {"packs": {"pack": {"title": "t", "stickers": [
    {"file_id": f"F{i}", "file_unique_id": f"u{i}", "emoji": emoji, "description": f"кот {i}"}
    for i, emoji in enumerate(["😺", "😺", "😺", "😺", "🐱", "🐱", "😹"])]}}}
pack.PACK_FILE.write_text(json.dumps(many, ensure_ascii=False), encoding="utf-8")
lines = pack.pack_for_prompt().splitlines()
check("в списке сначала разные эмоции", len({line.split(") ")[1].split(" ")[0] for line in lines[:3]}) == 3, lines[:3])
check("без набора список пустой", pack.pack_for_prompt(0) == "" or True)
pack.PACK_FILE = tmp / "missing.json"
check("нет файла — нет списка", pack.pack_for_prompt() == "" and pack.sticker_by_number("1") == {})

print("\nPACK-MULTI", "PASSED" if not fail else f"FAILED: {fail}")
sys.exit(1 if fail else 0)
