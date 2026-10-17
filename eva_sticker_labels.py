"""Ева (fork): перевести описания стикеров в короткие русские подписи.

Описания нужны двоим: персоне (в окне чата) и фильтру, который выбирает стикер по смыслу. Длинные
английские фразы «The image depicts a cat…» им мешают и съедают по 80 символов на строку промта.
Скрипт берёт уже собранные описания из ``~/eva-home/sticker_pack.json`` (и библиотеки) и переписывает
их короткими русскими подписями, пачками по нескольку штук за вызов — зрение не гоняется повторно.

    python3 eva_sticker_labels.py [--apply] [--batch 12]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, "/home/iizey/eva-hermes")

HOME = Path(os.environ.get("HERMES_HOME") or (Path.home() / "eva-home"))
PACK_FILE = HOME / "sticker_pack.json"
LIBRARY_FILE = HOME / "sticker_cache.json"
LOG = HOME / "logs" / "sticker_labels.log"
log = logging.getLogger("eva.sticker_labels")

SYSTEM = (
    "Ты переписываешь описания телеграм-стикеров короткими русскими подписями. Для каждого дай "
    "3-8 слов: что на картинке и что стикер выражает. Без вводных слов, без перевода текста с "
    "картинки, без нумерации внутри подписи, без точки в конце. Отвечай ровно столько строк, "
    "сколько дано описаний, по одной подписи на строку, в том же порядке."
)


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _ask(descriptions: list[str]) -> list[str]:
    from plugins.platforms.telegram.eva_gate import (_call, _endpoint, resolve_fallback,
                                                     resolve_reasoning_effort, resolve_target)
    provider, model, base_url = resolve_target()
    if not model:
        return []
    numbered = "\n".join(f"{i}. {text}" for i, text in enumerate(descriptions, start=1))
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"Описания:\n{numbered}\n\nПодписи по строкам:"}]
    effort = resolve_reasoning_effort()
    answer = None
    base, key = _endpoint(provider, base_url)
    if base and key:
        answer = _call(base, key, model, messages, timeout=90.0, reasoning_effort=effort,
                       max_tokens=60 * len(descriptions) + 100)
    if answer is None:
        fb_provider, fb_model, fb_base = resolve_fallback()
        fb_url, fb_key = _endpoint(fb_provider, fb_base)
        if fb_model and fb_url and fb_key:
            answer = _call(fb_url, fb_key, fb_model, messages, timeout=90.0,
                           reasoning_effort=effort, max_tokens=60 * len(descriptions) + 100)
    if not answer:
        return []
    lines = [" ".join(line.split()) for line in str(answer).splitlines()]
    lines = [re.sub(r"^\s*\d+[.)]\s*", "", line).strip(" .,;") for line in lines if line.strip()]
    lines = [line for line in lines if line]
    if len(lines) != len(descriptions):
        log.warning("модель вернула %d строк на %d описаний — пачку пропускаю", len(lines), len(descriptions))
        return []
    return lines


def _needs_rewrite(text: str) -> bool:
    """Английское или длинное описание — переписать; короткая русская подпись уже годится."""
    text = (text or "").strip()
    if not text:
        return False
    letters = [c for c in text if c.isalpha()]
    latin = sum(1 for c in letters if "a" <= c.lower() <= "z")
    if letters and latin / len(letters) > 0.4:
        return True
    return len(text) > 70


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--batch", type=int, default=12)
    args = ap.parse_args()
    HOME.joinpath("logs").mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(LOG, encoding="utf-8")])

    data = _load(PACK_FILE, {})
    packs = data.get("packs") or ({data.get("name") or "pack": data} if data.get("stickers") else {})
    targets = []
    for name, pack in packs.items():
        for entry in pack.get("stickers") or []:
            if _needs_rewrite(entry.get("description") or ""):
                targets.append((name, entry))
    print(f"подписей на переписывание: {len(targets)} из "
          f"{sum(len(p.get('stickers') or []) for p in packs.values())}")
    if not targets:
        return 0

    done = 0
    for start in range(0, len(targets), args.batch):
        chunk = targets[start:start + args.batch]
        labels = _ask([entry.get("description") or "" for _, entry in chunk])
        if not labels:
            continue
        for (name, entry), label in zip(chunk, labels):
            entry["description"] = label
            done += 1
            print(f"  {entry.get('emoji')} {label}")
        if args.apply and done:
            # сохраняем по ходу — прогонов на сотню подписей бывает много
            tmp = PACK_FILE.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(
                {"packs": packs, "updated_at": int(time.time())}, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, PACK_FILE)
    if args.apply:
        library = _load(LIBRARY_FILE, {})
        by_uid = {entry.get("file_unique_id"): entry for _, entry in targets}
        for uid, entry in by_uid.items():
            if uid in library:
                library[uid]["description"] = entry.get("description")
        tmp = LIBRARY_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(library, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, LIBRARY_FILE)
        print(f"\nпереписано подписей: {done}; файлы обновлены")
    else:
        print(f"\ndry-run: переписала бы {done} (нужен --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
