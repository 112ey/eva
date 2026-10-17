import importlib
mods = ["tui_gateway.launch_profile_policy", "tui_gateway.server", "gateway.run_turn", "gateway.run_adapters"]
for m in mods:
    try:
        importlib.import_module(m)
        print("OK  ", m)
    except Exception as exc:
        print("FAIL", m, type(exc).__name__, exc)
from tui_gateway.server import _load_enabled_toolsets
print("enabled toolsets(cli):", _load_enabled_toolsets("cli"))
print("enabled toolsets(telegram):", _load_enabled_toolsets("telegram"))
