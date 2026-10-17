import sys, os
sys.path.insert(0, "/home/iizey/eva-hermes")
os.environ.setdefault("HERMES_HOME", "/home/iizey/eva-home")
os.environ.setdefault("NVIDIA_BASE_URL", "http://127.0.0.1:8790/v1")
from eva_sticker_pack import pack_for_prompt, sticker_by_number
from plugins.platforms.telegram.eva_gate import classify

pack = pack_for_prompt()
cases = [
    ("[Паша] ахахах ты видел это", None),
    ("[Максим] я сдал экзамен на пять!", None),
    ("[Паша] ну ты и дурак", None),
    ("[Алексей] кот умер вчера", None),
    ("[Ева] как прошёл день? / [Паша] норм, устал только", None),
    ("[Паша] /pomogite kak nastroi'", None),
    ("[Паша] Ева, пойдёшь с нами гулять?", None),
    ("[Паша] Ева ты тупая / [Ева] с чего вдруг / [Паша] иди нафиг отсюда", None),
    ("[Паша] Ева, спасибо тебе большое, выручила", None),
    ("[Паша] Ева, посоветуй игру на вечер", None),
    ("[Паша] Ева, согласна что физика сложная?", None),
    ("[Паша] Ева, привет", None),
    ("[Паша] Ева, пока", None),
    ("[Паша] ахахахах ну ты выдал", None),
    ("[Паша] Ева, ты лучшая", None),
    ("[Паша] Ева, ты где потерялась?", None),
    ("[Паша] фууу, гадость какая", None),
    ("[Паша] мем (без подписи, прислали картинку)", None),
    ("[Паша] Ева, помоги с домашкой по геометрии", None),
    ("[Паша] эх, меня предки наказали, телефон забрали", None),
]
for incoming, _ in cases:
    verdict = classify([], incoming, stickers=pack, timeout=25)
    extra = ""
    if verdict and verdict[0] == "sticker":
        entry = sticker_by_number(verdict[1]) or {}
        extra = f" → {(entry.get('description') or '')[:60]}"
    print(f"{incoming[:52]:<54} → {verdict}{extra}")
