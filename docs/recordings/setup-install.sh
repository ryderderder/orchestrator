#!/usr/bin/env bash
# Build the clean throwaway environment for recording
# docs/recordings/install.tape. Re-run before every take.
#
#   ./setup-install.sh
#   TEAMCTL_RAW_BASE=http://127.0.0.1:8123 ./setup-install.sh   # private-repo mode
#
# Isolation guarantees — nothing touches the operator's real setup:
#   - HOME is /tmp/demo (scratch, rebuilt every run)
#   - TMUX_TMPDIR=/tmp/demo/.tmux-tmp so the installer's own
#     `tmux new-session -A -s teamctl` starts a scratch server, never the
#     operator's real one
#
# Pre-seeded so the recording matches a normal logged-in machine:
#   - empty ~/.claude.json and ~/.codex/auth.json (teamctl's documented
#     login-artifact detection is presence-based)
#   - a copy of the real codex models cache, so model suggestions in the
#     recording are real output
#
# TEAMCTL_RAW_BASE (optional): baked into the sandbox env for the
# installer's file downloads. While the repo is private, serve the checkout
# with `python3 -m http.server 8123 --bind 127.0.0.1` from the repo root and
# set TEAMCTL_RAW_BASE=http://127.0.0.1:8123 — same curl download code path.
set -euo pipefail

REAL_HOME="${REAL_HOME:-$HOME}"
IH=/tmp/demo

if [ -d "$IH/.tmux-tmp" ]; then
  env -u TMUX TMUX_TMPDIR="$IH/.tmux-tmp" tmux kill-server 2>/dev/null || true
fi
rm -rf "$IH"
mkdir -p "$IH/.tmux-tmp" "$IH/.codex" "$IH/.local/bin"
touch "$IH/.claude.json" "$IH/.codex/auth.json"
cp "$REAL_HOME/.codex/models_cache.json" "$IH/.codex/" 2>/dev/null || true

# clean minimal prompt; PATH re-pin (see setup-demo.sh for why)
{
  echo "export PATH=\"$IH/.local/bin:/opt/homebrew/bin:\$PATH\""
  echo "PS1='\\[\\e[1;36m\\]\$\\[\\e[0m\\] '"
} > "$IH/.bashrc"
cp "$IH/.bashrc" "$IH/.bash_profile"

# environment the tape sources before the take (Hide section)
cat > "$IH/env.sh" <<EOF
export HOME=$IH
unset TMUX TMUX_PANE
export TMUX_TMPDIR=$IH/.tmux-tmp
export PATH="$IH/.local/bin:\$PATH"
export SHELL=/bin/bash
cd $IH
EOF
if [ -n "${TEAMCTL_RAW_BASE:-}" ]; then
  echo "export TEAMCTL_RAW_BASE=$TEAMCTL_RAW_BASE" >> "$IH/env.sh"
fi

echo "install env ready at $IH (raw base: ${TEAMCTL_RAW_BASE:-github})"
