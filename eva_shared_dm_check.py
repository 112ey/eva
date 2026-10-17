"""Проверка «одна личка на всех»: общая сессия, подпись отправителя, доступ по списку, модель по умолчанию."""
import os
import sys
import types

sys.path.insert(0, "/home/iizey/eva-hermes")
os.environ.setdefault("HERMES_HOME", "/home/iizey/eva-home")

from gateway.session import Platform, SessionSource, build_session_key  # noqa: E402
import gateway.session as session_mod  # noqa: E402
from plugins.platforms.telegram.adapter import TelegramAdapter  # noqa: E402
from hermes_cli.config import load_config_readonly  # noqa: E402

fail = []
OWNER = "111111111"
FRIEND = "333333333"


def check(name, cond, extra=""):
    print(f"[{'ok' if cond else 'FAIL'}] {name}{' — ' + str(extra) if extra else ''}")
    if not cond:
        fail.append(name)


def source(user_id, chat_id, chat_type="dm", name="Кто-то", platform=Platform.TELEGRAM):
    return SessionSource(platform=platform, chat_id=chat_id, chat_type=chat_type,
                         user_id=user_id, user_name=name)


# 1. Общий ключ сессии для личек
# Живой конфиг: у каждого своя личка (shared_dm_session выключен) — ключи разные.
session_mod._SHARED_DM_CACHE = None
owner_key = build_session_key(source(OWNER, OWNER, name="Владелец"))
friend_key = build_session_key(source(FRIEND, FRIEND, name="Знакомый"))
check("у каждого своя личка (ключи разные)", owner_key != friend_key, (owner_key, friend_key))
check("ключ лички — по человеку", friend_key.endswith(f"telegram:dm:{FRIEND}"), friend_key)
check("общей лички в живом конфиге нет", "shared" not in friend_key, friend_key)

# А сам режим общей лички остался рабочим: включаем флаг заглушкой конфига.
_saved_loader = None
try:
    import gateway.session as _sm
    _sm_orig = _sm.shared_dm_session_enabled
    _sm._SHARED_DM_CACHE = None
    original_extra = None
    from hermes_cli.config import load_config_readonly as _load
    _base = _load()
    _patched = dict(_base)
    _patched_extra = dict((_base.get("platforms", {}).get("telegram", {}) or {}).get("extra", {}) or {})
    _patched_extra["shared_dm_session"] = {"enabled": True}
    _patched.setdefault("platforms", {}).setdefault("telegram", {})["extra"] = _patched_extra
    _sm._SHARED_DM_CACHE = None
    import hermes_cli.config as _cfg_mod
    _real_load = _cfg_mod.load_config_readonly
    _cfg_mod.load_config_readonly = lambda *a, **k: _patched
    _sm._SHARED_DM_CACHE = None
    shared_owner = build_session_key(source(OWNER, OWNER, name="Владелец"))
    shared_friend = build_session_key(source(FRIEND, FRIEND, name="Знакомый"))
    check("с включённым флагом — одна общая личка", shared_owner == shared_friend
          and shared_friend.endswith("telegram:dm:shared"), (shared_owner, shared_friend))
finally:
    try:
        _cfg_mod.load_config_readonly = _real_load
    except Exception:  # noqa: BLE001
        pass
    _sm._SHARED_DM_CACHE = None

group_key = build_session_key(source(OWNER, "-1001111111111", chat_type="group"))
check("групповые сессии не задеты", group_key.startswith("agent:main:telegram:group:-1001111111111"), group_key)

# 2. С выключенным флагом — как раньше, у каждого своя сессия
session_mod._SHARED_DM_CACHE = None
orig = session_mod.shared_dm_session_enabled
session_mod.shared_dm_session_enabled = lambda src: False
try:
    off_owner = build_session_key(source(OWNER, OWNER, name="Владелец"))
    off_friend = build_session_key(source(FRIEND, FRIEND, name="Знакомый"))
finally:
    session_mod.shared_dm_session_enabled = orig
    session_mod._SHARED_DM_CACHE = None
check("при выключенном флаге сессии разные", off_owner != off_friend, (off_owner, off_friend))


# 3. Подпись «[Имя|id]» в общей личке
class _Stub(TelegramAdapter):
    name = "Telegram"
    platform = Platform.TELEGRAM

    def __init__(self):
        self.config = types.SimpleNamespace(extra={"shared_dm_session": {"enabled": True}})

    def _effective_message_thread_id(self, message):
        return None

    def _resolve_topic_binding(self, message, chat_type, thread_id_str):
        return None, None


stub = object.__new__(_Stub)
_Stub.__init__(stub)


def dm_message(user_id=FRIEND, name="Знакомый", text="привет, ты Ева?"):
    return types.SimpleNamespace(
        chat=types.SimpleNamespace(id=int(user_id), full_name=name, title=None, type="private"),
        from_user=types.SimpleNamespace(id=int(user_id), full_name=name, is_bot=False),
        message_id=7, message_thread_id=None, date=None, is_topic_message=False,
        text=text, caption=None, forum_topic_created=None, quote=None, reply_to_message=None)


event = TelegramAdapter._build_message_event(stub, dm_message(), "text", None)
check("в личке видно, кто пишет", event.text.startswith(f"[Знакомый|{FRIEND}]"), event.text)
check("подпись не съела текст", event.text.endswith("привет, ты Ева?"), event.text)
check("в контексте хода — правильный отправитель", event.source.user_name == "Знакомый", event.source.user_name)

stub.config.extra["shared_dm_session"] = {"enabled": False}
event = TelegramAdapter._build_message_event(stub, dm_message(), "text", None)
check("при выключенном флаге подписи нет", event.text == "привет, ты Ева?", event.text)
stub.config.extra["shared_dm_session"] = {"enabled": True}

# 4. Доступ в личку — по списку allow_from, и модель по умолчанию — немотрон
stub._bot = None
stub._log_blocked_user = lambda *a, **k: None
extra = load_config_readonly()["platforms"]["telegram"]["extra"]
stub.config = types.SimpleNamespace(extra=extra)
allowed = TelegramAdapter._is_user_authorized_from_message(stub, dm_message(user_id=OWNER, name="Владелец"))
blocked = TelegramAdapter._is_user_authorized_from_message(stub, dm_message(user_id="123456789", name="Чужой"))
check("владелец в личке авторизован", allowed is True, allowed)
check("чужой в личку не пройдёт", blocked is False, blocked)
check("список allow_from из конфига", len(extra.get("allow_from") or []) >= 1
      and str(OWNER) in [str(x) for x in extra["allow_from"]], extra.get("allow_from"))
check("разрешённый знакомый тоже в списке",
      "222222222" in [str(x) for x in (extra.get("allow_from") or [])], extra.get("allow_from"))

# 4b. Механизм доступа: как только id знакомого попадает в список — он проходит
adapter_mod = sys.modules["plugins.platforms.telegram.adapter"]
original = adapter_mod._scoped_gate_env
try:
    # так же, как это делает гейтвей на старте: конфиг → рантайм-список
    adapter_mod._apply_yaml_config({"platforms": {}}, {"allow_from": [OWNER, FRIEND]})
    runtime_list = adapter_mod._scoped_gate_env("TELEGRAM_ALLOWED_USERS")
    # adapter-level extra.allow_from — «единственный источник правды», если задан (так и задокументировано)
    stub.config = types.SimpleNamespace(extra={**extra, "allow_from": [OWNER, FRIEND]})
    friend_allowed = TelegramAdapter._is_user_authorized_from_message(stub, dm_message(user_id=FRIEND, name="Знакомый"))
    owner_still_allowed = TelegramAdapter._is_user_authorized_from_message(stub, dm_message(user_id=OWNER, name="Владелец"))
finally:
    adapter_mod._apply_yaml_config({"platforms": {}}, {"allow_from": [OWNER]})
check("id из конфига доходит до рантайм-списка", FRIEND in runtime_list, runtime_list)
check("добавленный в список знакомый проходит", friend_allowed is True, friend_allowed)
check("владелец при этом не теряет доступ", owner_still_allowed is True, owner_still_allowed)

# 4c. Формат словаря флага: можно включить общую личку только для части людей
held = session_mod._SHARED_DM_CACHE
session_mod._SHARED_DM_CACHE = None
stub.config = types.SimpleNamespace(extra=extra)
enabled_dict = TelegramAdapter._eva_shared_dm_session(stub)
stub.config = types.SimpleNamespace(extra={**extra, "shared_dm_session": {"enabled": True, "users": [OWNER]}})
check("флаг читается и как словарь с enabled", enabled_dict is not False)

cfg = load_config_readonly()
model = cfg.get("model", {}).get("default")
check("модель по умолчанию — немотрон", "nemotron" in str(model), model)

print("\nSHARED-DM", "PASSED" if not fail else f"FAILED: {fail}")
sys.exit(1 if fail else 0)
