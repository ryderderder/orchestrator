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
#   --no-deps   skip dependency detection and install offers
#
# The installer never runs a package manager without asking first, and says
# so when a command will use sudo. Provider CLIs are never auto-installed;
# their official install one-liners are printed instead.
set -euo pipefail

BIN_DIR="${TEAMCTL_BIN_DIR:-$HOME/.local/bin}"
RAW_BASE="${TEAMCTL_RAW_BASE:-https://raw.githubusercontent.com/ryderderder/teamctl/main}"
FILES=(teamctl claude-statusline)
UNAME_S="$(uname -s 2>/dev/null || echo unknown)"

# ---- native Windows: not supported (teamctl needs tmux) -------------------
case "$UNAME_S:${OSTYPE:-}" in
  MSYS* | MINGW* | CYGWIN* | Windows_NT* | *:msys* | *:cygwin*)
    cat >&2 <<'EOF'
teamctl needs tmux, which does not run on native Windows.
Use WSL (Windows Subsystem for Linux) instead:
  1. In an elevated PowerShell:   wsl --install
  2. Reboot if prompted, open your WSL distro (e.g. Ubuntu), and re-run
     this installer inside it:
       curl -fsSL https://raw.githubusercontent.com/ryderderder/teamctl/main/install.sh | bash
Nothing was installed.
EOF
    exit 0
    ;;
esac

RUN_INIT="ask"
SKIP_DEPS=0
for arg in "$@"; do
  case "$arg" in
    --init) RUN_INIT="yes" ;;
    --no-init) RUN_INIT="no" ;;
    --no-deps) SKIP_DEPS=1 ;;
    *)
      echo "install.sh: unknown option '$arg' (supported: --init, --no-init, --no-deps)" >&2
      exit 2
      ;;
  esac
done

# ---- interactive prompts ---------------------------------------------------
# Answers are read from the terminal even under `curl | bash` (where stdin is
# the script itself). TEAMCTL_TTY overrides the answer source for testing.
TTY_IN="${TEAMCTL_TTY:-/dev/tty}"
HAVE_TTY=0
if { exec 3< "$TTY_IN"; } 2>/dev/null; then
  HAVE_TTY=1
fi

ask_yn() { # ask_yn "question " -> 0 = yes. Default (blank/EOF/no tty) = no.
  local ans
  [ "$HAVE_TTY" = 1 ] || return 1
  printf "%s" "$1" >&2
  read -r ans <&3 || return 1
  case "$ans" in
    y | Y | yes | YES) return 0 ;;
    *) return 1 ;;
  esac
}

# ---- install the binaries --------------------------------------------------
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

# ---- dependencies: detect, then OFFER to install ---------------------------
python_ok() {
  command -v python3 >/dev/null 2>&1 || return 1
  python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null
}

PKG_MGR=""
PKG_SUDO=0
if [ "$UNAME_S" = Darwin ]; then
  command -v brew >/dev/null 2>&1 && PKG_MGR=brew
elif [ "$UNAME_S" = Linux ]; then
  if command -v apt-get >/dev/null 2>&1; then
    PKG_MGR=apt-get
  elif command -v dnf >/dev/null 2>&1; then
    PKG_MGR=dnf
  elif command -v pacman >/dev/null 2>&1; then
    PKG_MGR=pacman
  fi
  if [ -n "$PKG_MGR" ] && [ "$(id -u)" != 0 ]; then
    PKG_SUDO=1
  fi
fi

run_pm() { # run the package manager, with sudo when required
  if [ "$PKG_SUDO" = 1 ]; then sudo "$@"; else "$@"; fi
}

pkg_name() { # dependency -> package name under $PKG_MGR
  case "$1" in
    tmux) echo tmux ;;
    python3)
      case "$PKG_MGR" in
        brew | pacman) echo python ;;
        *) echo python3 ;;
      esac
      ;;
  esac
}

install_dep() { # $1 = dependency name; returns non-zero on failure
  local pkg
  pkg="$(pkg_name "$1")"
  case "$PKG_MGR" in
    brew) brew install "$pkg" ;;
    apt-get)
      run_pm apt-get update -qq || true
      run_pm apt-get install -y "$pkg"
      ;;
    dnf) run_pm dnf install -y "$pkg" ;;
    pacman) run_pm pacman -S --noconfirm "$pkg" ;;
    *) return 1 ;;
  esac
}

manual_hint() {
  case "$1" in
    tmux) echo "  tmux:     https://github.com/tmux/tmux/wiki/Installing" ;;
    python3) echo "  python3:  version 3.11+ from https://www.python.org/downloads/ or your package manager" ;;
  esac
}

MISSING=()
command -v tmux >/dev/null 2>&1 || MISSING+=(tmux)
python_ok || MISSING+=(python3)

if [ ${#MISSING[@]} -gt 0 ]; then
  echo
  echo "missing dependencies: ${MISSING[*]}"
  if [ "$SKIP_DEPS" = 1 ]; then
    echo "(--no-deps: skipping install offers)"
    for dep in "${MISSING[@]}"; do manual_hint "$dep"; done
  elif [ -z "$PKG_MGR" ]; then
    echo "no supported package manager found (brew / apt-get / dnf / pacman)."
    echo "install these yourself:"
    for dep in "${MISSING[@]}"; do manual_hint "$dep"; done
  else
    if [ "$PKG_SUDO" = 1 ]; then
      echo "note: installs below run '$PKG_MGR' with sudo (you may be asked for your password)."
    fi
    TO_INSTALL=()
    if [ ${#MISSING[@]} -gt 1 ] &&
      ask_yn "Install all missing dependencies (${MISSING[*]}) via $PKG_MGR? [y/N] "; then
      TO_INSTALL=("${MISSING[@]}")
    else
      for dep in "${MISSING[@]}"; do
        if ask_yn "Install $dep via $PKG_MGR? [y/N] "; then
          TO_INSTALL+=("$dep")
        fi
      done
    fi
    if [ ${#TO_INSTALL[@]} -gt 0 ]; then
      for dep in "${TO_INSTALL[@]}"; do
        if ! install_dep "$dep"; then
          echo "warning: '$PKG_MGR' failed to install $dep" >&2
        fi
      done
    fi
    # re-check and print manual hints for whatever is still missing
    STILL=()
    command -v tmux >/dev/null 2>&1 || STILL+=(tmux)
    python_ok || STILL+=(python3)
    if [ ${#STILL[@]} -gt 0 ]; then
      echo "still missing: ${STILL[*]} — install manually:"
      for dep in "${STILL[@]}"; do manual_hint "$dep"; done
    fi
  fi
fi

# ---- provider CLIs: never auto-installed, one-liners printed instead -------
HAVE_PROVIDER=0
for p in claude codex grok; do
  command -v "$p" >/dev/null 2>&1 && HAVE_PROVIDER=1
done
if [ "$HAVE_PROVIDER" = 0 ]; then
  cat <<'EOF'

no provider CLI found (claude / codex / grok). teamctl needs at least one.
Their installers change, so install from the official sources yourself:
  Claude Code:  curl -fsSL https://claude.ai/install.sh | bash
                (docs: https://code.claude.com/docs/en/setup)
  Codex CLI:    curl -fsSL https://chatgpt.com/codex/install.sh | sh
                (docs: https://github.com/openai/codex)
  Grok CLI:     curl -fsSL https://x.ai/cli/install.sh | bash
                (docs: https://docs.x.ai)
then log in with the CLI once, and re-run `teamctl init`.
EOF
fi

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    echo "warning: $BIN_DIR is not on your PATH. Add it, e.g.:" >&2
    echo "  export PATH=\"$BIN_DIR:\$PATH\"" >&2
    ;;
esac

# ---- offer the onboarding wizard -------------------------------------------
if [ "$RUN_INIT" = "ask" ]; then
  RUN_INIT="no"
  if ask_yn "Run 'teamctl init' (onboarding wizard) now? [y/N] "; then
    RUN_INIT="yes"
  fi
fi

if [ "$RUN_INIT" = "yes" ]; then
  if [ "$HAVE_TTY" = 1 ] && [ "$TTY_IN" = /dev/tty ]; then
    "$BIN_DIR/teamctl" init < /dev/tty
  else
    "$BIN_DIR/teamctl" init --yes
  fi
else
  echo "done. Run '$BIN_DIR/teamctl init' any time to configure defaults."
fi
