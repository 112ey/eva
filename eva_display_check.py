"""Что реально видит её гейтвей в чате: настройки вывода для telegram."""
import os, sys
os.environ.setdefault("HERMES_HOME", "/home/iizey/eva-home")
sys.path.insert(0, "/home/iizey/eva-hermes")
from hermes_cli.config_effective import load_user_config_effective
from gateway.display_config import resolve_display_setting
cfg = load_user_config_effective()
keys = ("tool_progress", "interim_assistant_messages", "long_running_notifications",
        "busy_ack_detail", "busy_steer_ack_enabled", "suppress_warning_notifications", "show_reasoning")
for k in keys:
    print(f"  telegram.{k} = {resolve_display_setting(cfg, 'telegram', k, None)!r}")
extra = cfg.get("platforms", {}).get("telegram", {}).get("extra", {})
print("  command_menu =", extra.get("command_menu"))
print("  error_dm_chat_id =", extra.get("error_dm_chat_id"))
