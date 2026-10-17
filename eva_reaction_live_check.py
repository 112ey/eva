"""Живая проверка: реакция через её же код ставится на реальное сообщение в Telegram."""
import asyncio, json, os, re, sys, urllib.parse, urllib.request, types
sys.path.insert(0, "/home/iizey/eva-hermes")
os.environ.setdefault("HERMES_HOME", "/home/iizey/eva-home")

tok = re.search(r'^TELEGRAM_BOT_TOKEN=(.*)$', open(os.path.expanduser("~/eva-home/.env")).read(), re.M).group(1).strip()
B = f"http://127.0.0.1:8081/bot{tok}"


def api(method, **params):
    data = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}).encode()
    req = urllib.request.Request(f"{B}/{method}", data=data)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


class Bot:
    """Тонкая обёртка: тот же вызов, что делает адаптер, но к живому Bot API."""
    async def set_message_reaction(self, chat_id=None, message_id=None, reaction=None):
        res = api("setMessageReaction", chat_id=chat_id, message_id=message_id,
                  reaction=json.dumps([{"type": "emoji", "emoji": reaction}] if reaction else []))
        if not res.get("ok"):
            raise RuntimeError(res.get("description"))
        return True


from plugins.platforms.telegram.adapter import TelegramAdapter  # noqa: E402


class _Stub(TelegramAdapter):
    name = "Telegram"


stub = object.__new__(_Stub)
stub._bot = Bot()
sent = api("sendMessage", chat_id="111111111", text="проверка реакций через код")
mid = sent["result"]["message_id"]
stub._eva_last_inbound = {"111111111": str(mid)}

ok = asyncio.run(TelegramAdapter._eva_react_to_last(stub, "111111111", "🔥"))
print(f"[{'ok' if ok else 'FAIL'}] реакция поставлена кодом адаптера на сообщение {mid}")
hidden = asyncio.run(TelegramAdapter._eva_react_to_last(stub, "111111111", "🍕"))
print(f"[{'ok' if hidden is False else 'FAIL'}] неподдерживаемый эмодзи не ушёл (вернулось False)")
api("deleteMessage", chat_id="111111111", message_id=mid)
print("тестовое сообщение удалено")
print("REACTIONS-LIVE", "PASSED" if (ok and hidden is False) else "FAILED")
sys.exit(0 if (ok and hidden is False) else 1)
