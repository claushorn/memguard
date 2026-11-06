#!/usr/bin/env bash
# Install / remove the memguard OOM watchdog as a per-user launchd agent (macOS).
#
#   tools/install_memwatch.sh              # render plist, load it, show status
#   tools/install_memwatch.sh --uninstall  # unload and remove
#
# Exemptions (processes never suspended or killed) live OUTSIDE this repo, one
# command-line substring per line:  ~/.config/memguard/exempt
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.memguard.memwatch"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

case "${1:-install}" in
  --uninstall)
    launchctl unload "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    echo "removed $PLIST"
    ;;
  install)
    UV="$(command -v uv)" || { echo "uv not found on PATH" >&2; exit 1; }
    (cd "$REPO" && uv sync --quiet)
    mkdir -p "$REPO/logs" "$HOME/Library/LaunchAgents"
    sed -e "s#@REPO@#$REPO#g" -e "s#@UV@#$UV#g" \
        "$REPO/tools/$LABEL.plist.template" > "$PLIST"
    plutil -lint "$PLIST" >/dev/null
    launchctl unload "$PLIST" 2>/dev/null || true
    launchctl load "$PLIST"
    sleep 2
    launchctl list | grep "$LABEL" || { echo "NOT RUNNING — see $REPO/logs/memwatch.err.log" >&2; exit 1; }
    tail -3 "$REPO/logs/memwatch.log" 2>/dev/null || true
    ;;
  *)
    echo "usage: $0 [--uninstall]" >&2; exit 2 ;;
esac
