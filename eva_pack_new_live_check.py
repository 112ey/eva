"""Живая проверка: стикер из нового набора реально уходит её ботом (и сразу удаляется)."""
import asyncio, json, os, re, sys, urllib.parse, urllib.request, types
sys.path.insert(0, "/home/iizey/eva-hermes")
os.environ.setdefault("HERMES_HOME", "/home/iizey/eva-home")
import eva_sticker_pack as sp

tok = re.search(r'^TELEGRAM_BOT_TOKEN=(.*)$', open(os.path.expanduser("~/eva-home/.env")).read(), re.M).group(1).strip()
B = f"http://127.0.0.1:8081/bot{tok}"

def api(method, **params):
    data = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{B}/{method}", data=data), timeout=40) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())

entries = sp._entries()
order = sp._pick_order(entries, 40)
new_pack = [i for i in order if entries[i]["pack"].startswith("kotiki")]
print(f"стикеров всего: {len(entries)}, в списке фильтра: {len(order)}, из нового набора: {len(new_pack)}")
# находим номер, за которым стоит стикер нового набора
number = next(str(n) for n, i in enumerate(order, start=1) if entries[i]["pack"].startswith("kotiki"))
entry = sp.sticker_by_number(number)
print(f"проверяю номер {number}: {entry.get('emoji')} {entry.get('description')} [{entry.get('pack')}]")
sent = api("sendSticker", chat_id=111111111, sticker=entry["file_id"])
ok = bool(sent.get("ok"))
print("[ok] стикер нового набора уходит" if ok else f"[FAIL] не ушёл: {sent.get('description')}")
if ok:
    deleted = api("deleteMessage", chat_id=111111111, message_id=sent["result"]["message_id"])
    print("[ok] и удалён (следов не осталось)" if deleted.get("ok") else f"[warn] удалить не вышло: {deleted.get('description')}")

listing = sp.pack_for_prompt().splitlines()
print("пример списка для фильтра:")
for line in listing[:3]:
    print("  ", line[:70])
print("PACK-NEW-LIVE", "PASSED" if ok and len(new_pack) else "FAILED")
sys.exit(0 if ok and len(new_pack) else 1)
