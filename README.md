# teamctl

**teamctl** turns a tmux window into an AI agent team: a *lead* agent (or you)
in the left pane manages *teammates* — Claude Code, Codex, or Grok CLI
sessions — as tmux panes tiled in a square grid to the right. It spawns
interactive teammates, dispatches headless tasks and reads their results back
as JSON, routes work to whichever provider is currently available, tracks real
usage where providers expose it, and tears teammates down cleanly
(process-tree-verified, no orphans). Single-file Python, stdlib only.

## Requirements

- macOS or Linux
- [tmux](https://github.com/tmux/tmux) (teamctl runs inside a tmux session)
- Python 3.11+ (3.9+ works, but config-file support needs `tomllib` from 3.11)
- At least one provider CLI installed and logged in:
  [Claude Code](https://code.claude.com) (`claude`), OpenAI Codex CLI
  (`codex`), or Grok CLI (`grok`)

## Install

```sh
curl -fsSL https://raw.githubusercontent.com/ryderderder/teamctl/main/install.sh | bash
```

Or from a checkout:

```sh
git clone https://github.com/ryderderder/teamctl && cd teamctl && ./install.sh
```

The installer copies `teamctl` and `claude-statusline` to `~/.local/bin`
(warning you if that's not on your PATH) and offers to run the onboarding
wizard. It is safe to re-run.

Then, inside a tmux session:

```sh
teamctl init        # onboarding wizard (optional but recommended)
```

## Quickstart

```sh
# Interactive teammate: opens a Claude Code pane seeded with a prompt.
teamctl spawn reviewer --provider claude --model opus \
    --prompt "Review the diff on this branch for correctness."

# See who's active.
teamctl list

# Type a follow-up instruction into a running teammate's pane.
teamctl send reviewer "Focus on the error handling in server.py."

# Headless task: runs in a watchable pane, result lands in a handoff dir.
teamctl dispatch researcher --provider codex \
    --task "Summarize the TODOs in this repo as JSON." --cwd ~/myproject

# Read the result back (blocks until done; fails fast if the teammate dies).
teamctl result researcher --wait

# Another turn in the same provider session.
teamctl followup researcher --task "Now rank them by effort."

# Let teamctl pick the provider: first available among claude > codex > grok,
# skipping anything not installed, not logged in, or known-exhausted.
teamctl route helper --task "Draft release notes from the last 10 commits."
teamctl route helper --task "..." --dry-run     # preview the choice + command

# Provider availability and real usage.
teamctl providers
teamctl usage

# Clean teardown: kills the whole process tree, verifies it, closes the pane.
teamctl shutdown reviewer
```

## The lead-agent workflow

The intended shape: **you (or a lead AI agent) sit in the left pane; teammates
tile as a square grid to the right.** The first teammate takes the right half;
each further teammate splits the largest teammate pane in whichever direction
keeps panes square-ish, so four teammates form a 2×2 grid beside the lead. The
lead pane is never re-split.

Each teammate pane carries sticky `@role` / `@model` tmux user options, so
with the optional tmux block from `teamctl init` every pane border shows
`role · model` — labels the provider CLI can't overwrite (unlike pane
titles), and which don't rely on `#()` shell commands (which some tmux builds
don't execute in status formats). The active pane's `role · model` also
appears in the status bar.

A lead agent drives the same commands programmatically: `dispatch` writes the
task to a per-teammate handoff directory
(`~/.local/state/agent-team/<role>/`), the teammate's stdout is captured to
`result.json`, stderr to `error.log`, and an exit `status` file makes
`result --wait` reliable — including failing fast when a teammate dies
without reporting.

## Configuration

`teamctl init` walks you through everything below, shows exactly what it
changes, and prints revert steps. Run it with `--yes` for non-interactive
defaults (config file only; no tmux or Claude Code changes).

`~/.config/agent-team/config.toml`:

```toml
[output]
verbosity = "normal"        # terse | normal | detailed

[providers.claude]
model = "opus"              # default --model for claude teammates
effort = "high"             # default --effort

[providers.codex]
model = ""                  # blank/absent: the CLI's own default
effort = "high"             # passed as -c model_reasoning_effort=...

[providers.grok]
effort = "high"             # grok has no persistent effort setting of its
                            # own; teamctl passes this per invocation

[routing]
preference = ["claude", "codex", "grok"]   # order `route` prefers
```

Command-line `--model` / `--effort` always override the config. State lives
in `~/.local/state/agent-team/state.json` (override with `$TEAMCTL_STATE`).

`teamctl init` also offers (default **no**, backups made first):

- a marker-guarded block in `~/.tmux.conf` for the pane-border and status-bar
  `role · model` labels;
- installing `claude-statusline` (shows `model · effort · ctx N%` in Claude
  Code) and adding the `statusLine` key to `~/.claude/settings.json` — skipped
  if a `statusLine` key already exists.

## Uninstall

```sh
./uninstall.sh
```

Removes the binaries, removes the tmux marker block (backup made first), and
removes the `statusLine` settings key if — and only if — it points at this
tool's script (backup made first). Config and state files are left in place;
the script prints the one-liner to remove them too.

## Limitations (honest ones)

- **Usage numbers exist only where providers expose them locally.** Codex
  writes rate-limit windows to its session logs, so `teamctl usage` shows real
  percentages and reset times for it. Claude and Grok don't expose account
  quota locally — Claude Code shows live context in its own status line
  (in-TUI `/usage` has more), and `teamctl usage` says "not exposed" rather
  than inventing numbers.
- **Exhaustion signals are best-effort.** `route` skips a provider only after
  its output was seen to contain a limit/auth error, or Codex's own log shows
  100% on the 5h window; signals with a known reset time auto-expire.
- **`#()` in tmux formats is not portable** — some tmux builds don't execute
  shell commands in status formats at all. That's why the pane labels use
  `@role`/`@model` user options instead. No shell runs in your status bar.
- **`send` types into a terminal.** It sends literal keys plus Enter; there's
  no acknowledgment protocol. For machine-readable round-trips use
  `dispatch`/`result`.
- **macOS/Linux only** (uses `flock`, `pgrep`, POSIX signals). Not tested on
  Windows/WSL.
- Provider CLIs must already be installed and logged in; teamctl never
  handles credentials itself.

## License

MIT — see [LICENSE](LICENSE).
