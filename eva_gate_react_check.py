"""Проверка новых вердиктов фильтра: ДА (писать) / РЕАКЦИЯ (смайлик) / НЕТ (тишина)."""
import sys

sys.path.insert(0, "/home/iizey/eva-hermes")
sys.path.insert(0, "/home/iizey/eva-hermes/plugins/platforms/telegram")

from plugins.platforms.telegram.eva_gate import classify  # noqa: E402
from eva_reactions import allowed as reaction_allowed  # noqa: E402

fail = []
CHAT = ["[Паша] кто-нибудь видел мой зарядник?", "[Максим] ахахах", "[Ева] ну и ладно"]


def check(name, cond, extra=""):
    print(f"[{'ok' if cond else 'FAIL'}] {name}{' — ' + str(extra) if extra else ''}")
    if not cond:
        fail.append(name)


CASES = [
    ("мем без слов", "[Максим] ахахах вот мем, ору", ("react",)),
    ("милое фото", "[Паша] (фото) вот кот спит, лапки раскинул", ("react", "reply")),
    ("чужой успех", "[Роман] сдал экзамен наконец", ("react", "reply")),
    ("болтовня", "[Паша] ну ладно, пошёл спать", ("silent",)),
    ("просьба посмотреть", "[Владелец] (фото) смотри какой кошак", ("reply",)),
    ("к ней вопрос", "[Владелец] Ева, как дела?", ("reply",)),
    ("горе у человека", "[Алексей] у меня вчера кот умер", ("reply",)),
]

for name, message, expected in CASES:
    verdict = classify(CHAT, message)
    if verdict is None:
        check(f"{name}: фильтр ответил", False, "нет решения (провайдер?)")
        continue
    kind, emoji = verdict
    check(f"{name}: вердикт {kind} в {expected}", kind in expected, (kind, emoji))
    if kind == "react":
        check(f"{name}: эмодзи подходит Telegram", reaction_allowed(emoji) and emoji == emoji, emoji)

print("\nGATE-REACT", "PASSED" if not fail else f"FAILED: {fail}")
sys.exit(1 if fail else 0)
