"""Fork self-check: identity source, diary block, tool surface. Run: eva --run-module eva_check"""
import os
from pathlib import Path

home = Path(os.environ.get("HERMES_HOME", ""))
print("HERMES_HOME:", home)
print("PERSONA.md exists:", (home / "PERSONA.md").exists(), "| SOUL.md exists:", (home / "SOUL.md").exists())

from agent import prompt_builder as pb

soul = pb.load_soul_md(home_override=home)
print("IDENTITY loaded:", bool(soul), "| first 160 chars:")
print("   ", (soul or pb.DEFAULT_AGENT_IDENTITY)[:160].replace("\n", " "))
print("DEFAULT_AGENT_IDENTITY head:", pb.DEFAULT_AGENT_IDENTITY[:80].replace("\n", " "))

idx = pb.build_skills_system_prompt(
    available_tools={"skills_list", "skill_view", "skill_manage"},
    available_toolsets={"skills"}, compact_categories=None,
    skills_dir_override=home / "diary")
print("PROMPT BLOCK (start):")
print("   ", (idx or "")[:400].replace("\n", " | "))

import toolsets
print("CORE TOOLS:", toolsets._HERMES_CORE_TOOLS)
print("skills toolset:", toolsets.get_toolset("skills", include_registry=False))
print("telegram toolset members:", (toolsets.get_toolset("hermes-telegram", include_registry=False) or {}).get("includes"))

try:
    import model_tools
    model_tools.discover_builtin_tools()
    from tools.registry import registry
    for meth in ("get_all_tool_names", "tool_names", "names"):
        if hasattr(registry, meth):
            val = getattr(registry, meth)
            names = sorted(val() if callable(val) else val)
            print("REGISTERED TOOLS (%d):" % len(names), names[:20])
            break
    else:
        print("registry methods:", [m for m in dir(registry) if not m.startswith("_")][:20])
except Exception as exc:
    print("registry check failed:", type(exc).__name__, exc)
