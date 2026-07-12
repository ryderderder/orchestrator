#!/usr/bin/env bash
# Build the environment for recording demo-v2.tape — the REAL-PROVIDER hero
# demo (grok researches, claude builds, codex reviews). Re-run before every
# take: teammate state AND the seeded tinylog.py must be fresh (the builder
# edits it for real).
#
#   ./setup-demo-live.sh [git-revision]     # pin teamctl to a pushed rev
#
# Isolation (same guarantees as setup-demo.sh, one honest difference):
#   - HOME is /tmp/teamhome-live (scratch, rebuilt every run)
#   - tmux runs on its own socket /tmp/teamhome-live/tmux.sock — NEVER the
#     default server; the tape always passes -S
#   - TEAMCTL_STATE + config are scratch; your real teamctl setup untouched
#   - DIFFERENT from the shell-provider harness: provider auth/session dirs
#     are symlinked in and the CLIs WRITE THROUGH them (session logs, their
#     own state) — exactly as any normal CLI run does. Real tokens are
#     spent. That is the point of this recording (no fakery).
#
# REQUIRED PREFLIGHT before rolling a take (verify, don't assume):
#   source /tmp/teamhome-live/env.sh
#   claude -p 'say ok' --output-format json     # one smoke turn per provider
#   codex exec 'say ok'
#   grok -p 'say ok'
# If a CLI needs a dot-path this script doesn't link yet, add the symlink
# below and re-verify. (Which paths each CLI needs is machine/version
# dependent — the smoke test is the source of truth.)
set -euo pipefail

REAL_HOME="${REAL_HOME:-$HOME}"
REPO="${TEAMCTL_REPO:-$(cd "$(dirname "$0")/../.." && pwd)}"
DH=/tmp/teamhome-live

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
  echo "warning: recording from the working tree — pin a pushed revision for a shippable take" >&2
  cp "$REPO/teamctl" "$DH/bin/teamctl"
fi
chmod +x "$DH/bin/teamctl"

# provider auth + session dirs: symlinked, WRITE-THROUGH (see header).
# ~/.claude (dir) is included alongside ~/.claude.json — interactive-auth
# CLIs keep more than one artifact; extend this list if preflight fails.
for p in .codex .claude .claude.json .grok; do
  [ -e "$REAL_HOME/$p" ] && ln -s "$REAL_HOME/$p" "$DH/$p"
done

# the config a configured user would have: explicit routing preference and a
# slightly narrower lead pane so three teammate panes get readable width
cat > "$DH/.config/agent-team/config.toml" <<'EOF'
[output]
verbosity = "normal"

[lead]
delegation = "ask"

[routing]
preference = ["codex", "claude", "grok"]

[layout]
lead_width = 42
EOF

# the seeded task target: a small, legible, REAL file the builder will edit
cat > "$DH/work/tinylog.py" <<'EOF'
#!/usr/bin/env python3
"""tinylog — filter a plain-text log file by level.

usage: tinylog.py LOGFILE [--level LEVEL]

Log lines look like:  2026-07-12 10:02:11 INFO  message text
"""
import argparse
import sys


def parse_line(line: str):
    parts = line.rstrip("\n").split(None, 3)
    if len(parts) < 4:
        return None
    date, time, level, message = parts
    return {"ts": f"{date} {time}", "level": level, "message": message}


def main() -> int:
    ap = argparse.ArgumentParser(prog="tinylog")
    ap.add_argument("logfile")
    ap.add_argument("--level", default="", help="only show this level")
    args = ap.parse_args()

    try:
        lines = open(args.logfile, encoding="utf-8").readlines()
    except OSError as e:
        print(f"tinylog: {e}", file=sys.stderr)
        return 1

    for line in lines:
        entry = parse_line(line)
        if entry is None:
            continue
        if args.level and entry["level"] != args.level.upper():
            continue
        print(f'{entry["ts"]}  {entry["level"]:<5}  {entry["message"]}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
EOF

cat > "$DH/work/app.log" <<'EOF'
2026-07-12 10:01:58 INFO  server started on :8080
2026-07-12 10:02:03 WARN  slow query (412ms) on /orders
2026-07-12 10:02:11 ERROR POST /orders 500 — unhandled KeyError
2026-07-12 10:02:14 INFO  retry succeeded
EOF

# clean minimal prompt for lead and teammate panes; PATH re-pin is
# load-bearing on macOS (path_helper reorders PATH in login shells and
# /usr/bin/python3 has no tomllib -> teamctl silently ignores the config)
{
  echo "export PATH=\"$DH/bin:/opt/homebrew/bin:\$PATH\""
  echo "PS1='\\[\\e[1;36m\\]\$\\[\\e[0m\\] '"
} > "$DH/.bashrc"
cp "$DH/.bashrc" "$DH/.bash_profile"

# scratch tmux conf: role · model border labels, bare status bar
cat > "$DH/tmux.conf" <<'EOF'
set -g default-shell /bin/bash
set -g automatic-rename off
set -g status-right ''
set-option -g pane-border-status top
set-option -g pane-border-format '#{?#{@model}, #{@role} · #{@model} ,}'
set-option -ga status-right ' #{?#{@model},│ #{@role} · #{@model} ,}'
EOF

# environment the tape sources in its Hide section
cat > "$DH/env.sh" <<EOF
export HOME=$DH
unset TMUX TMUX_PANE
export TEAMCTL_STATE=$DH/.local/state/agent-team/state.json
export PATH="$DH/bin:\$PATH"
export SHELL=/bin/bash
cd $DH/work
EOF

echo "live-demo env ready at $DH (teamctl: ${REV:-working tree})"
echo "NEXT: run the per-provider preflight smoke tests before 'vhs demo-v2.tape'"
