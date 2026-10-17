"""Что реально решают ворота её Telegram-адаптера для группы."""
import os, sys
os.environ.setdefault("HERMES_HOME", "/home/iizey/eva-home")
sys.path.insert(0, "/home/iizey/eva-hermes")
from hermes_cli.config_effective import load_user_config_effective
cfg = load_user_config_effective()
extra = cfg.get("platforms", {}).get("telegram", {}).get("extra", {}) or {}
keys = ("group_policy", "dm_policy", "require_mention", "group_allowed_chats", "allowed_chats", "eva_gate", "free_response_chats",
        "guest_mode", "exclusive_bot_mentions", "observe_unmentioned_group_messages",
        "group_allow_from", "allow_from", "free_response_topics", "mention_patterns")
for k in keys:
    print(f"  extra.{k} = {extra.get(k)!r}")
import re
env = open(os.path.expanduser("~/eva-home/.env")).read()
tg = [n for n in re.findall(r"^(TELEGRAM_[A-Z_]+)", env, re.M)]
print("  env:", tg)
