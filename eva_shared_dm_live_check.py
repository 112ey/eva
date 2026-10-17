"""Живая проверка: стор гейтвея по общему ключу отдаёт ту же сессию, что и личка владельца."""
import asyncio, os, sys
sys.path.insert(0, "/home/iizey/eva-hermes")
os.environ.setdefault("HERMES_HOME", "/home/iizey/eva-home")
from gateway.session import Platform, SessionSource, SessionStore  # noqa: E402


class Cfg:
    profile = "default"
    multiplex_profiles = False
    home = None


def src(user_id):
    return SessionSource(platform=Platform.TELEGRAM, chat_id=user_id, chat_type="dm",
                         user_id=user_id, user_name="кто-то")


class _Cfg2:
    """Минимум того, что нужно стору: папка и профиль (как в гейтвее — config.sessions_dir, config)."""
    profile = "default"
    multiplex_profiles = False


from pathlib import Path  # noqa: E402

sessions_dir = Path(os.environ.get("HERMES_HOME", "/home/iizey/eva-home")) / "sessions"
store = SessionStore(sessions_dir, _Cfg2())
a = store.get_or_create_session(src("111111111"))
b = store.get_or_create_session(src("333333333"))
owner_row = store.get_or_create_session(src("111111111"))
print("личка владельца →", a.session_id)
print("личка знакомого →", b.session_id)
print("ключи:", a.session_key, "|", b.session_key)
ok = a.session_id == b.session_id and a.session_key == b.session_key == "agent:main:telegram:dm:shared"
print("SHARED-DM-LIVE", "PASSED" if ok else "FAILED")
sys.exit(0 if ok else 1)
