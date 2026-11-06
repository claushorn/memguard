#!/bin/bash
# "Uninstall memguard.app" — stops the watchdog, removes the Claude Code hook and the files.
# Keeps ~/.config/memguard (your exemption list).   --yes: no dialogs
set -euo pipefail
YES=0; [ "${1:-}" = "--yes" ] && YES=1
DEST="$HOME/Library/Application Support/memguard"
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

if [ $YES = 0 ]; then
    osascript -e 'display dialog "Uninstall memguard? The watchdog stops and the Claude Code hook is removed." buttons {"Cancel", "Uninstall"} default button 2 with title "memguard"' >/dev/null 2>&1 || exit 0
fi
[ -x "$DEST/tools/install_memwatch.sh" ] && "$DEST/tools/install_memwatch.sh" --uninstall
[ -x "$DEST/tools/install_agent_hook.sh" ] && [ -f "$HOME/.claude/settings.json" ] && "$DEST/tools/install_agent_hook.sh" --uninstall
rm -rf "$DEST"
[ $YES = 1 ] || osascript -e 'display dialog "memguard was removed." buttons {"OK"} with title "memguard"' >/dev/null
