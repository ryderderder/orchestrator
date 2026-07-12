#!/usr/bin/env bash
# Build the isolated environment for recording docs/recordings/demo.tape.
# Re-run before every take (state must be fresh).
#
#   ./setup-demo.sh [git-revision]
#
# With a revision, the teamctl under test is taken from `git show REV:teamctl`
# (record from pushed code, not a possibly-dirty working tree); without one,
# the working-tree teamctl is used.
#
# Isolation guarantees — nothing touches the operator's real setup:
#   - HOME is /tmp/teamhome (scratch, rebuilt every run)
#   - tmux runs on its own socket /tmp/teamhome/tmux.sock (never the
#     default server; the tape must always pass -S)
#   - TEAMCTL_STATE points into the scratch home
#   - real provider artifacts are reachable READ-ONLY via symlinks, so
#     auth detection and `teamctl usage` show real data (teamctl only
#     reads these paths)
set -euo pipefail

REAL_HOME="${REAL_HOME:-$HOME}"
REPO="${TEAMCTL_REPO:-$(cd "$(dirname "$0")/../.." && pwd)}"
DH=/tmp/teamhome

# kill any leftover scratch server from a previous take (its own socket only)
if [ -S "$DH/tmux.sock" ]; then
  env -u TMUX tmux -S "$DH/tmux.sock" kill-server 2>/dev/null || true
fi
rm -rf "$DH"
mkdir -p "$DH/bin" "$DH/.local/state/agent-team" "$DH/.config/agent-team" "$DH/work"

REV="${1:-}"
if [ -n "$REV" ]; then
  git -C "$REPO" show "$REV:teamctl" > "$DH/bin/teamctl"
else
  cp "$REPO/teamctl" "$DH/bin/teamctl"
fi
chmod +x "$DH/bin/teamctl"

# read-only visibility into real provider auth/usage artifacts
[ -e "$REAL_HOME/.codex" ] && ln -s "$REAL_HOME/.codex" "$DH/.codex"
[ -e "$REAL_HOME/.claude.json" ] && ln -s "$REAL_HOME/.claude.json" "$DH/.claude.json"
[ -e "$REAL_HOME/.grok" ] && ln -s "$REAL_HOME/.grok" "$DH/.grok"

# the config a user has after setup: an explicit routing preference, so
# `route` shows preference-based reasoning instead of the alphabetical
# fallback disclaimer
cat > "$DH/.config/agent-team/config.toml" <<'EOF'
[output]
verbosity = "normal"

[lead]
delegation = "ask"

[routing]
preference = ["codex", "claude", "grok"]
EOF

# clean minimal prompt for lead and teammate panes.
# NOTE: tmux default-shell starts a LOGIN bash (.bash_profile), teammate
# panes exec an interactive non-login bash (.bashrc) — provide both.
# The PATH re-pin matters: /etc/profile's path_helper (macOS) reorders
# PATH and puts /usr/bin's python3 (3.9, no tomllib) ahead of homebrew,
# which makes teamctl silently ignore the TOML config.
{
  echo "export PATH=\"$DH/bin:/opt/homebrew/bin:\$PATH\""
  echo "PS1='\\[\\e[1;36m\\]\$\\[\\e[0m\\] '"
} > "$DH/.bashrc"
cp "$DH/.bashrc" "$DH/.bash_profile"

# scratch tmux conf: the teamctl pane-border block (role · model labels)
# plus a bare status bar (no hostname/clock leaking into the recording)
cat > "$DH/tmux.conf" <<'EOF'
set -g default-shell /bin/bash
set -g automatic-rename off
set -g status-right ''
set-option -g pane-border-status top
set-option -g pane-border-format '#{?#{@model}, #{@role} · #{@model} ,}'
set-option -ga status-right ' #{?#{@model},│ #{@role} · #{@model} ,}'
EOF

# environment the tape sources before attaching (Hide section)
cat > "$DH/env.sh" <<EOF
export HOME=$DH
unset TMUX TMUX_PANE
export TEAMCTL_STATE=$DH/.local/state/agent-team/state.json
export PATH="$DH/bin:\$PATH"
export SHELL=/bin/bash
cd $DH/work
EOF

echo "demo env ready at $DH (teamctl: ${REV:-working tree})"
