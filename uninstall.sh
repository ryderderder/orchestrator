#!/usr/bin/env bash
# teamctl uninstaller — reverses what install.sh and `teamctl init` set up:
#   1. removes the binaries from ~/.local/bin (or TEAMCTL_BIN_DIR)
#   2. removes the teamctl marker block from ~/.tmux.conf (backup made first)
#   3. removes the statusLine key from ~/.claude/settings.json — but only if
#      it points at our claude-statusline script (backup made first)
# Per-user data (~/.config/agent-team, ~/.local/state/agent-team) is left in
# place; the exact rm command is printed at the end.
set -euo pipefail

BIN_DIR="${TEAMCTL_BIN_DIR:-$HOME/.local/bin}"
TMUX_CONF="$HOME/.tmux.conf"
SETTINGS="$HOME/.claude/settings.json"

# 1. binaries
for f in teamctl claude-statusline; do
  if [ -f "$BIN_DIR/$f" ]; then
    rm -f "$BIN_DIR/$f"
    echo "removed $BIN_DIR/$f"
  fi
done

# 2. tmux marker block
if [ -f "$TMUX_CONF" ] && grep -qF '# --- BEGIN teamctl ---' "$TMUX_CONF"; then
  cp "$TMUX_CONF" "$TMUX_CONF.bak-teamctl-uninstall"
  awk '
    $0 == "# --- BEGIN teamctl ---" { skip = 1; next }
    $0 == "# --- END teamctl ---"   { skip = 0; next }
    !skip { print }
  ' "$TMUX_CONF.bak-teamctl-uninstall" > "$TMUX_CONF"
  echo "removed teamctl block from $TMUX_CONF (backup: $TMUX_CONF.bak-teamctl-uninstall)"
  echo "if tmux is running, reload the config and reset the options the block set:"
  echo "  tmux source-file ~/.tmux.conf"
  echo "  tmux set-option -gu pane-border-status; tmux set-option -gu pane-border-format"
  echo "  tmux set-option -gu status-right; tmux set-option -gu @teamctl_status_added"
fi

# 3. Claude Code statusLine key — only if it points at our script
if [ -f "$SETTINGS" ] && command -v python3 >/dev/null 2>&1; then
  python3 - "$SETTINGS" <<'PY'
import json
import os
import shutil
import sys

path = sys.argv[1]
try:
    with open(path) as fh:
        data = json.load(fh)
except Exception:
    print(f"could not parse {path}; leaving it untouched", file=sys.stderr)
    sys.exit(0)

sl = data.get("statusLine")
if not isinstance(sl, dict):
    sys.exit(0)  # no statusLine key: nothing to do

cmd = sl.get("command", "")
ours = ("~/.local/bin/claude-statusline",
        os.path.expanduser("~/.local/bin/claude-statusline"))
if cmd in ours:
    shutil.copy2(path, path + ".bak-teamctl-uninstall")
    del data["statusLine"]
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    print(f"removed statusLine key from {path} "
          f"(backup: {path}.bak-teamctl-uninstall)")
else:
    print(f"statusLine in {path} does not point at "
          "~/.local/bin/claude-statusline; leaving it untouched")
PY
fi

echo "note: per-user data was left in place; remove it with:"
echo "  rm -rf ~/.config/agent-team ~/.local/state/agent-team"
echo "uninstall complete."
