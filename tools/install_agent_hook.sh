#!/usr/bin/env bash
# Register memguard's agent hook in Claude Code, so memwatch's warnings reach the AGENT.
#
#   tools/install_agent_hook.sh              # add to ~/.claude/settings.json (all sessions)
#   tools/install_agent_hook.sh --uninstall
#   SETTINGS=/path/settings.json tools/install_agent_hook.sh   # another settings file
#
# Adds a PostToolUse (all tools) and a UserPromptSubmit command hook running
# `python -I -m memguard.agent_hook`. Idempotent; the previous file is kept as
# settings.json.bak. Sessions already running pick the hook up when Claude Code reloads
# its settings (check with /hooks); new sessions get it immediately.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SETTINGS="${SETTINGS:-$HOME/.claude/settings.json}"
MODE="${1:-install}"
[ -x "$REPO/.venv/bin/python" ] || (cd "$REPO" && uv sync --quiet)

"$REPO/.venv/bin/python" - "$SETTINGS" "$MODE" "$REPO/.venv/bin/python" <<'PY'
import json, os, shutil, sys
path, mode, python = sys.argv[1], sys.argv[2], sys.argv[3]
COMMAND = f'"{python}" -I -m memguard.agent_hook'
MARK = "memguard.agent_hook"
EVENTS = {"PostToolUse": "*", "UserPromptSubmit": None}

settings = {}
if os.path.exists(path):
    with open(path, encoding="utf-8") as f:
        settings = json.load(f)
    shutil.copy2(path, path + ".bak")
hooks = settings.setdefault("hooks", {})

for event in EVENTS:                       # drop any previous memguard entry
    groups = [
        {**g, "hooks": [h for h in g.get("hooks", []) if MARK not in h.get("command", "")]}
        for g in hooks.get(event, [])
    ]
    hooks[event] = [g for g in groups if g["hooks"]]
    if not hooks[event]:
        del hooks[event]

if mode == "install":
    for event, matcher in EVENTS.items():
        group = {"hooks": [{"type": "command", "command": COMMAND, "timeout": 10}]}
        if matcher is not None:
            group = {"matcher": matcher, **group}
        hooks.setdefault(event, []).append(group)
elif mode != "--uninstall":
    sys.exit(f"usage: install_agent_hook.sh [--uninstall]  (got {mode!r})")
if not hooks:
    del settings["hooks"]

os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, "w", encoding="utf-8") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")
print(("installed" if mode == "install" else "removed") + f" memguard agent hook in {path}")
PY
