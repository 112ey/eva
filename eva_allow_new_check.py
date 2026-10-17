"""Проверка доступа нового собеседника в личку Евы (живой конфиг)."""
import sys, types, os
sys.path.insert(0, "/home/iizey/eva-hermes")
os.environ.setdefault("HERMES_HOME", "/home/iizey/eva-home")
fail = []
def check(name, cond, extra=""):
    print(f"[{'ok' if cond else 'FAIL'}] {name}{' — ' + str(extra) if extra else ''}")
    if not cond:
        fail.append(name)

import re
text = open(os.path.expanduser("~/eva-home/config.yaml"), encoding="utf-8").read()
# хватает разбора списка allow_from (yaml в этом питоне нет)
block = re.search(r"^      allow_from:\n((?:        .*\n)+)", text, re.M).group(1)
allowed = re.findall(r"^        - '([^']+)'", block, re.M)
print("allow_from:", allowed)
check("владелец в списке", "111111111" in allowed)
check("новый собеседник в списке", "222222222" in allowed)
check("посторонний НЕ в списке", "111222333" not in allowed)
check("политика личек — allowlist", "dm_policy: allowlist" in text)
check("чужие сообщения игнорируются", "unauthorized_dm_behavior: ignore" in text)
check("группы по-прежнему открыты", "group_allow_from: '*'" in text)
check("одна общая личка включена", re.search(r"shared_dm_session:\n        enabled: true", text) is not None)
check("служебные команды только владельцу", "owner_only_commands: true" in text)
check("ошибки по-прежнему владельцу", "error_dm_chat_id: '111111111'" in text)

# ключ сессии у обоих собеседников один — Ева не заводит каждому отдельный разговор
from gateway.session import shared_dm_session_enabled, build_session_key  # noqa: E402
from gateway.config import Platform  # noqa: E402

def source(user_id):
    return types.SimpleNamespace(platform=Platform.TELEGRAM, user_id=user_id, chat_type="dm",
                                 chat_id="222222222", thread_id=None, profile=None)

check("общая личка читается из живого конфига", shared_dm_session_enabled(source("111111111")) is True)
# ключ сессии у владельца и у знакомого совпадает → Ева ведёт ОДИН разговор, а не два
key_owner = build_session_key(source("111111111"))
key_guest = build_session_key(types.SimpleNamespace(platform=Platform.TELEGRAM, user_id="222222222",
                                                    chat_type="dm", chat_id="222222222", thread_id=None, profile=None))
check("один разговор на двоих (ключ сессии общий)", key_owner == key_guest, f"{key_owner} / {key_guest}")
check("в ключе есть признак общей лички", "shared" in str(key_owner), key_owner)

print("\nALLOW-NEW", "PASSED" if not fail else f"FAILED: {fail}")
sys.exit(1 if fail else 0)
