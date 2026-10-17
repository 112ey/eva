"""Why is skill_manage 'недоступен'? Print the enabled toolset/tool resolution for cli+telegram."""
import os
from pathlib import Path

print("HERMES_HOME:", os.environ.get("HERMES_HOME"))

import toolsets

for plat in ("cli", "telegram"):
    for fn in ("get_enabled_toolsets", "_load_enabled_toolsets", "resolve_enabled_toolsets",
               "enabled_toolsets_for_platform"):
        f = getattr(toolsets, fn, None)
        if f is None:
            continue
        try:
            val = f(plat)
        except Exception as exc:
            print(f"{plat}: {fn} raised {type(exc).__name__}: {exc}")
            continue
        print(f"{plat}: {fn} -> {val}")
        try:
            names = sorted(toolsets.get_tool_names_for_toolsets(val)) if hasattr(toolsets, "get_tool_names_for_toolsets") else None
        except Exception as exc:
            names = f"err {exc}"
        print("   names:", names)
        break

# config view
from hermes_cli.config import load_config
cfg = load_config() or {}
print("platform_toolsets:", cfg.get("platform_toolsets"))
print("tools section:", cfg.get("tools"))

# availability of the three tools through the registry check
import model_tools
model_tools.discover_builtin_tools()
from tools.registry import registry
for meth in ("is_tool_available", "tool_available", "check_tool_available", "available"):
    f = getattr(registry, meth, None)
    if f is None:
        continue
    for t in ("skills_list", "skill_view", "skill_manage"):
        try:
            print("  ", meth, t, "->", f(t))
        except Exception as exc:
            print("  ", meth, t, "raised", type(exc).__name__, exc)
    break
else:
    print("registry availability methods:", [m for m in dir(registry) if "avail" in m or "check" in m])
