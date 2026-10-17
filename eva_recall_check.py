"""Проверка вспоминания: как поиск по её дневнику отвечает на реальные реплики."""
import os
import sys

os.environ.setdefault("HERMES_HOME", "/home/iizey/eva-home")
sys.path.insert(0, "/home/iizey/eva-hermes")

from eva_memory import diary_pages, rank, recall_block  # noqa: E402

pages = diary_pages()
print(f"страниц в дневнике: {len(pages)}")
for p in pages:
    print(f"  · {p.name}: {' '.join(p.body.split())[:70]}")

print("\n=== поиск ===")
for query in ("Ева, как там Алексей вообще?",
              "что ты знаешь про человека, который тебя добавил?",
              "привет, ты помнишь вчерашний день?",
              "какой у тебя любимый напиток?",
              "расскажи про зарядник"):
    top = rank(query)[:3]
    print(f"\nзапрос: {query}")
    if not top:
        print("   ничего не нашлось")
    for score, page in top:
        print(f"   {score:6.2f}  {page.name}")
    block = recall_block(query)
    print("   блок:", "пусто" if not block else block.splitlines()[1][:100] + "…")
