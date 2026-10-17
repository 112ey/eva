"""Показать, какие темы (ветки) Ева знает: `eva --run-module eva_topics_show`."""
import json
import os
from pathlib import Path

import eva_topics


def main() -> None:
    if not Path(eva_topics.TOPICS_FILE).exists():
        print("файл тем пуст — она узнаёт названия из сообщений в ветках")
        return
    data = json.loads(Path(eva_topics.TOPICS_FILE).read_text(encoding="utf-8"))
    for chat_id, rows in data.items():
        print(f"\nчат {chat_id}:")
        for thread_id, name in sorted(eva_topics.topics(chat_id).items(), key=lambda kv: int(kv[0])):
            seen = (rows.get(thread_id) or {}).get("last_seen")
            print(f"  id {thread_id:>4}  {name}" + (f"   (последний раз {seen})" if seen else ""))
        print(f"  адаптер бы написал в тему для «нашла новый мем» → {eva_topics.best_thread(chat_id, 'нашла новый мем, ору')}")


if __name__ == "__main__":
    main()
