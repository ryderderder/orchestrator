#!/usr/bin/env bash
# teamctl installer — installs `teamctl` and `claude-statusline` into
# ~/.local/bin (override with TEAMCTL_BIN_DIR). Safe to re-run.
#
# From a checkout:   ./install.sh
# One-liner:         curl -fsSL https://raw.githubusercontent.com/ryderderder/teamctl/main/install.sh | bash
#
# Options:
#   --init      run `teamctl init` after installing (no prompt)
#   --no-init   skip the `teamctl init` offer
set -euo pipefail

BIN_DIR="${TEAMCTL_BIN_DIR:-$HOME/.local/bin}"
RAW_BASE="${TEAMCTL_RAW_BASE:-https://raw.githubusercontent.com/ryderderder/teamctl/main}"
FILES=(teamctl claude-statusline)

RUN_INIT="ask"
for arg in "$@"; do
  case "$arg" in
    --init) RUN_INIT="yes" ;;
    --no-init) RUN_INIT="no" ;;
    *)
      echo "install.sh: unknown option '$arg' (supported: --init, --no-init)" >&2
      exit 2
      ;;
  esac
done

# A checkout has the files next to this script; a curl|bash run does not
# and downloads them from the repo instead.
SRC_DIR=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]:-}" ]; then
  SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

mkdir -p "$BIN_DIR"
for f in "${FILES[@]}"; do
  if [ -n "$SRC_DIR" ] && [ -f "$SRC_DIR/$f" ]; then
    cp "$SRC_DIR/$f" "$BIN_DIR/$f"
    echo "installed $BIN_DIR/$f (copied from $SRC_DIR)"
  else
    curl -fsSL "$RAW_BASE/$f" -o "$BIN_DIR/$f"
    echo "installed $BIN_DIR/$f (downloaded)"
  fi
  chmod +x "$BIN_DIR/$f"
done

# Non-fatal environment checks.
if ! command -v tmux >/dev/null 2>&1; then
  echo "warning: tmux not found on PATH — teamctl needs tmux to run." >&2
fi
if command -v python3 >/dev/null 2>&1; then
  if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    echo "warning: python3 is older than 3.11 — config-file support (tomllib) needs 3.11+." >&2
  fi
else
  echo "warning: python3 not found on PATH — teamctl is a Python 3 script." >&2
fi

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    echo "warning: $BIN_DIR is not on your PATH. Add it, e.g.:" >&2
    echo "  export PATH=\"$BIN_DIR:\$PATH\"" >&2
    ;;
esac

# Offer the onboarding wizard. When stdin is a pipe (curl|bash) the wizard
# needs the terminal, so both the prompt and the wizard read /dev/tty.
if [ "$RUN_INIT" = "ask" ]; then
  RUN_INIT="no"
  if { true < /dev/tty; } 2>/dev/null; then
    printf "Run 'teamctl init' (onboarding wizard) now? [y/N] " > /dev/tty || true
    if read -r ans < /dev/tty; then
      case "$ans" in
        y | Y | yes | YES) RUN_INIT="yes" ;;
      esac
    fi
  fi
fi

if [ "$RUN_INIT" = "yes" ]; then
  if { true < /dev/tty; } 2>/dev/null; then
    "$BIN_DIR/teamctl" init < /dev/tty
  else
    "$BIN_DIR/teamctl" init --yes
  fi
else
  echo "done. Run '$BIN_DIR/teamctl init' any time to configure defaults."
fi
