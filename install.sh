#!/usr/bin/env bash
# orchestrator installer — installs `orchestrator` into ~/.local/bin (override with
# TEAMCTL_BIN_DIR). Safe to re-run. Since v0.4.0 the statusline is a
# `orchestrator statusline` subcommand, not a separate script.
#
# From a checkout:   ./install.sh
# One-liner:         curl -fsSL https://raw.githubusercontent.com/ryderderder/orchestrator/main/install.sh | bash
#
# Default flow on an interactive terminal: install, offer to install missing
# dependencies (tmux defaults to yes — it is a hard requirement), then enter
# a tmux session and run the zero-question `orchestrator init` EXPRESS setup,
# leaving you inside a working, already-configured session in seconds.
#
# Options:
#   --no-init      skip the setup/tmux bootstrap at the end
#   --init         kept for compatibility (express setup runs by default)
#   --custom-init  run the rich `orchestrator init --custom` wizard instead of express
#   --no-deps      skip dependency detection and install offers
#
# The installer never runs a package manager without asking first, and says
# so when a command will use sudo. Provider CLIs are never auto-installed;
# their official install one-liners are printed instead.
set -euo pipefail

BIN_DIR="${TEAMCTL_BIN_DIR:-$HOME/.local/bin}"
RAW_BASE="${TEAMCTL_RAW_BASE:-https://raw.githubusercontent.com/ryderderder/orchestrator/main}"
# One binary since v0.4.0: the statusline is a `orchestrator statusline`
# subcommand, not a separate script.
FILES=(orchestrator)
UNAME_S="$(uname -s 2>/dev/null || echo unknown)"

# ---- native Windows: not supported (orchestrator needs tmux) -------------------
case "$UNAME_S:${OSTYPE:-}" in
  MSYS* | MINGW* | CYGWIN* | Windows_NT* | *:msys* | *:cygwin*)
    cat >&2 <<'EOF'
orchestrator needs tmux, which does not run on native Windows.
Use WSL (Windows Subsystem for Linux) instead:
  1. In an elevated PowerShell:   wsl --install
  2. Reboot if prompted, open your WSL distro (e.g. Ubuntu), and re-run
     this installer inside it:
       curl -fsSL https://raw.githubusercontent.com/ryderderder/orchestrator/main/install.sh | bash
Nothing was installed.
EOF
    exit 0
    ;;
esac

# ---- WSL: presents as Linux and is fully supported — say so ---------------
# (the native-Windows refusal above does NOT catch WSL: uname is Linux.
# Pure-bash, bash-3.2-safe check — no external tools, so it works however
# minimal the PATH. TEAMCTL_PROC_VERSION is a test seam only.)
# NOTE redirection order: stderr must be nulled BEFORE the input file is
# opened — bash applies redirections left-to-right, so `< file 2>/dev/null`
# printed "No such file or directory" on every macOS run (no /proc there).
_pv=""
{ IFS= read -r _pv || true; } 2>/dev/null < "${TEAMCTL_PROC_VERSION:-/proc/version}" || true
case "$_pv" in
  *[Mm]icrosoft*)
    echo "detected WSL${WSL_DISTRO_NAME:+ ($WSL_DISTRO_NAME)} — proceeding as Linux (supported)."
    ;;
esac

RUN_INIT="yes"
INIT_ARGS=""
SKIP_DEPS=0
for arg in "$@"; do
  case "$arg" in
    --init) RUN_INIT="yes" INIT_ARGS="" ;;
    --custom-init) RUN_INIT="yes" INIT_ARGS=" --custom" ;;
    --no-init) RUN_INIT="no" ;;
    --no-deps) SKIP_DEPS=1 ;;
    *)
      echo "install.sh: unknown option '$arg' (supported: --init, --custom-init, --no-init, --no-deps)" >&2
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

ask_yn() { # ask_yn "question " [yes] -> 0 = yes. Blank/EOF -> the default
  # ("yes" if given, else no). No tty at all -> ALWAYS no, whatever the
  # default: nothing is installed without a terminal to ask on.
  local ans def="${2:-no}"
  [ "$HAVE_TTY" = 1 ] || return 1
  printf "%s" "$1" >&2
  if ! read -r ans <&3; then
    ans=""
  fi
  case "$ans" in
    y | Y | yes | YES) return 0 ;;
    n | N | no | NO) return 1 ;;
    "") [ "$def" = yes ] ;;
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

# A pre-v0.4.0 install may have left a separate claude-statusline script;
# `orchestrator init` / `orchestrator update` migrate the settings.json wiring and
# remove the orphan, but drop the stale binary here too so the fold is clean.
rm -f "$BIN_DIR/claude-statusline" 2>/dev/null || true

# ---- record the install source so `orchestrator update` knows where to pull ----
# source=git-clone (checkout with a git remote) | local-copy (plain dir) |
# curl (one-liner). `orchestrator update` re-fetches from here later; config and
# state stay untouched.
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/agent-team"
json_escape() { printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'; }

SOURCE="curl" REPO_URL="" REF="main" SRC_DIR_META="" RAW_BASE_META=""
if [ -n "$SRC_DIR" ] && [ -f "$SRC_DIR/orchestrator" ]; then
  SRC_DIR_META="$SRC_DIR"
  if git -C "$SRC_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    SOURCE="git-clone"
    REPO_URL="$(git -C "$SRC_DIR" config --get remote.origin.url 2>/dev/null || true)"
    REF="$(git -C "$SRC_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
  else
    SOURCE="local-copy"
    REF=""
  fi
else
  RAW_BASE_META="$RAW_BASE"
  case "$RAW_BASE" in
    https://raw.githubusercontent.com/*)
      _rest="${RAW_BASE#https://raw.githubusercontent.com/}"
      _owner="${_rest%%/*}"
      _rest="${_rest#*/}"
      _repo="${_rest%%/*}"
      REF="${_rest#*/}"
      REPO_URL="https://github.com/$_owner/$_repo.git"
      ;;
  esac
fi
INSTALLED_VERSION="$(sed -n 's/^VERSION = "\(.*\)"$/\1/p' "$BIN_DIR/orchestrator" | head -1)"
mkdir -p "$STATE_DIR"
cat > "$STATE_DIR/install-meta.json" <<EOF
{
  "source": "$(json_escape "$SOURCE")",
  "repo": "$(json_escape "$REPO_URL")",
  "raw_base": "$(json_escape "$RAW_BASE_META")",
  "ref": "$(json_escape "$REF")",
  "src_dir": "$(json_escape "$SRC_DIR_META")",
  "bin_dir": "$(json_escape "$BIN_DIR")",
  "version": "$(json_escape "$INSTALLED_VERSION")",
  "installed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)"
}
EOF
echo "recorded install source ($SOURCE) for \`orchestrator update\`"

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
        # tmux is a hard requirement, so its prompt defaults to YES;
        # everything else stays an explicit opt-in.
        if [ "$dep" = tmux ]; then
          if ask_yn "Install tmux via $PKG_MGR? [Y/n] " yes; then
            TO_INSTALL+=("$dep")
          fi
        elif ask_yn "Install $dep via $PKG_MGR? [y/N] "; then
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
# Detection is per provider and never offers one that is already installed:
# installed CLIs get their real state (ready / quiet / locked out) from
# orchestrator itself; missing ones get their official install one-liner.
install_hint() {
  case "$1" in
    claude)
      echo "    Claude Code:  curl -fsSL https://claude.ai/install.sh | bash"
      echo "                  (docs: https://code.claude.com/docs/en/setup)"
      ;;
    codex)
      echo "    Codex CLI:    curl -fsSL https://chatgpt.com/codex/install.sh | sh"
      echo "                  (docs: https://github.com/openai/codex)"
      ;;
    grok)
      echo "    Grok CLI:     curl -fsSL https://x.ai/cli/install.sh | bash"
      echo "                  (docs: https://docs.x.ai)"
      ;;
    gemini)
      echo "    Gemini CLI:   npm install -g @google/gemini-cli   (or: brew install gemini-cli)"
      echo "                  (docs: https://geminicli.com)"
      ;;
  esac
}

HAVE_PROVIDER=0
MISSING_PROVIDERS=()
for p in claude codex grok gemini; do
  if command -v "$p" >/dev/null 2>&1; then
    HAVE_PROVIDER=1
  else
    MISSING_PROVIDERS+=("$p")
  fi
done

provider_found_lines() { # PATH-only fallback when orchestrator cannot run yet
  for p in claude codex grok gemini; do
    if command -v "$p" >/dev/null 2>&1; then
      echo "  $p    found"
    else
      echo "  $p    not installed"
    fi
  done
}

echo
echo "providers:"
# orchestrator's own state lattice: ready / quiet / locked out / not installed
STATE_LINES=""
if python_ok; then
  STATE_LINES="$("$BIN_DIR/orchestrator" providers 2>/dev/null | tail -n +2)" ||
    STATE_LINES=""
fi
if [ -n "$STATE_LINES" ]; then
  printf '%s\n' "$STATE_LINES" | sed 's/^/  /'
else
  provider_found_lines
fi

if [ ${#MISSING_PROVIDERS[@]} -gt 0 ]; then
  if [ "$HAVE_PROVIDER" = 0 ]; then
    echo
    echo "no provider CLI found (claude / codex / grok / gemini). orchestrator needs at least one."
    echo "Their installers change, so install from the official sources yourself:"
  else
    echo
    echo "  add more providers any time (official installers):"
  fi
  for p in "${MISSING_PROVIDERS[@]}"; do
    install_hint "$p"
  done
  echo "  then sign the CLI in once, and re-run \`orchestrator init\`."
fi

# ---- PATH check (A3) --------------------------------------------------------
# A bare warning here is WIPED by the tmux takeover below (exec clears the
# screen). So: offer to append the export to the user's shell profile, and
# if they decline, hand the note to `orchestrator init` (TEAMCTL_PATH_NOTE) so it
# re-prints DURABLY inside the post-setup frame the user actually ends on.
PATH_NOTE=""
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    PATH_NOTE="$BIN_DIR"
    profile=""
    case "${SHELL:-}" in
      *zsh) profile="$HOME/.zshrc" ;;
      *bash) profile="$HOME/.bashrc" ;;
      *) profile="$HOME/.profile" ;;
    esac
    echo "note: $BIN_DIR is not on your PATH." >&2
    if [ -n "$profile" ] &&
      ask_yn "Append the PATH line to $profile? [y/N] "; then
      {
        echo ""
        echo "# Added by orchestrator installer"
        echo "export PATH=\"$BIN_DIR:\$PATH\""
      } >> "$profile"
      echo "appended to $profile — run 'source $profile' or open a new shell." >&2
      PATH_NOTE=""   # handled: no need to re-surface it in the frame
    else
      echo "  add it yourself: export PATH=\"$BIN_DIR:\$PATH\"" >&2
    fi
    ;;
esac

# ---- bootstrap: land the user inside tmux with setup already done ----------
# Default flow (opt out with --no-init): if we're already inside tmux, run
# the express setup here; otherwise enter (or create) a 'orchestrator' tmux
# session and run it inside — express asks ZERO questions and prints what it
# chose (`--custom-init` swaps in the rich wizard). `< "$TTY_IN"` matters:
# under curl|bash stdin is the pipe, and tmux needs the real terminal.
#
# TEAMCTL_FIRST_RUN=1 turns on init's installer orientation tail (A2: the
# curl|bash user lands in tmux with no idea what to do — the frame shows the
# spawn + lead-on moves). TEAMCTL_PATH_NOTE re-surfaces the PATH note (A3).
TEAMCTL_Q="$(printf "%q" "$BIN_DIR/orchestrator")"
BOOTSTRAP_ENV="TEAMCTL_FIRST_RUN=1"
[ -n "$PATH_NOTE" ] && BOOTSTRAP_ENV="$BOOTSTRAP_ENV TEAMCTL_PATH_NOTE=$(printf "%q" "$PATH_NOTE")"
BOOTSTRAP_CMD="$BOOTSTRAP_ENV $TEAMCTL_Q init$INIT_ARGS; exec \${SHELL:-/bin/sh}"
export TEAMCTL_FIRST_RUN=1
[ -n "$PATH_NOTE" ] && export TEAMCTL_PATH_NOTE="$PATH_NOTE"
if [ "$RUN_INIT" = "no" ]; then
  echo "done. Run '$BIN_DIR/orchestrator init' any time to configure defaults."
elif [ -n "${TMUX:-}" ]; then
  # already inside tmux: run the setup right here
  if [ "$HAVE_TTY" = 1 ] && [ "$TTY_IN" = /dev/tty ]; then
    # shellcheck disable=SC2086 — INIT_ARGS is "" or " --custom"
    "$BIN_DIR/orchestrator" init$INIT_ARGS < /dev/tty
  else
    # no terminal to ask on: express, which asks nothing anyway
    "$BIN_DIR/orchestrator" init --yes
  fi
elif command -v tmux >/dev/null 2>&1 && [ "$HAVE_TTY" = 1 ]; then
  # tmux refuses a literal /dev/tty as its client terminal ("can't use
  # /dev/tty"), so resolve the concrete device from stderr — still the real
  # terminal under curl|bash. With TEAMCTL_TTY set (tests), use it as-is.
  if [ "$TTY_IN" != /dev/tty ]; then
    TTYDEV="$TTY_IN"
  else
    TTYDEV="$(tty 0<&2 2>/dev/null)" || TTYDEV=""
  fi
  if [ -n "$TTYDEV" ] && [ -e "$TTYDEV" ]; then
    echo "entering tmux (session 'orchestrator') and running the express setup…"
    # 0<> (read-write) is load-bearing: `<` opens the tty O_RDONLY, and the
    # tmux client then writes its whole UI through that same fd — on a
    # faithful pty that meant a BLACK SCREEN for the real first-run user
    # (46 bytes drawn vs ~2k fixed; found and verified by the demo-recorder).
    exec tmux new-session -A -s orchestrator "$BOOTSTRAP_CMD" 0<> "$TTYDEV"
  else
    echo "could not find your terminal device; finish setup with:"
    echo "  tmux new-session -A -s orchestrator '$BIN_DIR/orchestrator init$INIT_ARGS; exec \$SHELL'"
  fi
else
  echo "finish setup once you have a terminal and tmux:"
  echo "  tmux new-session -A -s orchestrator '$BIN_DIR/orchestrator init$INIT_ARGS; exec \$SHELL'"
fi
