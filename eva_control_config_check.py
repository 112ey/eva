"""Проверка: адаптер видит владельца выключателя из конфига её дома."""
import os, sys, types
sys.path.insert(0, "/home/iizey/eva-hermes")
os.environ.setdefault("HERMES_HOME", "/home/iizey/eva-home")
from hermes_cli.config import load_config_readonly
from plugins.platforms.telegram.adapter import TelegramAdapter


class _Stub(TelegramAdapter):
    name = "Telegram"


cfg = load_config_readonly()
extra = cfg.get("platforms", {}).get("telegram", {}).get("extra", {})
print("extra.eva_control =", extra.get("eva_control"))
stub = object.__new__(_Stub)
stub.config = types.SimpleNamespace(extra=extra)
owners = TelegramAdapter._eva_control_owner_ids(stub)
print("владельцы выключателя:", owners)

# и состояние, которое адаптер реально видит, — из её дома,
# но ПЕРЕКЛЮЧАЕМ его только во временном файле: тест не должен трогать живой мью.
import tempfile as _tempfile
from pathlib import Path as _Path
from eva_control import STATE, set_muted
import eva_control as _control

_live = STATE
_control.STATE = _Path(_tempfile.mkdtemp()) / "control.json"
print("файл состояния (живой):", _live)
set_muted(False)          # гарантируем чистый старт проверки
stub._eva_muted_cache = None
before = TelegramAdapter._eva_muted(stub)
set_muted(True, by="111111111")
stub._eva_muted_cache = None
during = TelegramAdapter._eva_muted(stub)
set_muted(False)
stub._eva_muted_cache = None
after = TelegramAdapter._eva_muted(stub)
print(f"адаптер видит: до мьюта={before}, при мьюте={during}, после={after}")
ok = owners == {"111111111"} and str(_live).endswith("control.json") and "eva-home" in str(_live) \
     and before is False and during is True and after is False
print("CONTROL-CONFIG", "PASSED" if ok else "FAILED")
sys.exit(0 if ok else 1)
