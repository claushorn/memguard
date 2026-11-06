#!/usr/bin/env bash
# Arm the large-data load guard in ANOTHER project's venv (pandas / pyarrow reads).
#
#   tools/install_memguard.sh /path/to/project/.venv             # install
#   tools/install_memguard.sh /path/to/project/.venv --check     # report, change nothing
#   tools/install_memguard.sh /path/to/project/.venv --uninstall
#
# HOW it works: a single `.pth` in the target venv's site-packages. CPython executes
# `.pth` lines at interpreter startup — a bare path line is added to sys.path, and an
# `import` line is executed:
#
#     /path/to/memguard
#     import memguard.arm
#
# Nothing is copied, so it can never go stale against the source, and because uv never
# installed it as a package there is no dist-info for `uv sync` to prune.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${1:?usage: $0 <venv> [--check|--uninstall]}"
MODE="${2:-install}"

[ -d "$VENV" ] || { echo "no venv at $VENV" >&2; exit 1; }
SITE_PACKAGES="$(echo "$VENV"/lib/python*/site-packages)"
[ -d "$SITE_PACKAGES" ] || { echo "could not locate site-packages under $VENV" >&2; exit 1; }
PTH="$SITE_PACKAGES/memguard.pth"

armed() {
    "$VENV/bin/python" -c \
        "import pandas; print(getattr(pandas.read_csv,'_memguard_wrapped',False))" 2>/dev/null \
        || echo "(pandas not installed — arms once it is)"
}

case "$MODE" in
  --check)
    echo "venv          : $VENV"
    echo "hook present  : $([ -f "$PTH" ] && echo yes || echo NO)"
    echo "guard armed   : $(armed)"
    [ -f "$PTH" ] || exit 1
    ;;
  --uninstall)
    rm -f "$PTH"; echo "removed $PTH" ;;
  install)
    printf '%s\nimport memguard.arm\n' "$REPO" > "$PTH"
    echo "wrote $PTH"
    echo "guard armed   : $(armed)"
    ;;
  *)
    echo "usage: $0 <venv> [--check|--uninstall]" >&2; exit 2 ;;
esac
