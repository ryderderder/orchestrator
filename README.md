# teamctl

[![ci](https://github.com/ryderderder/teamctl/actions/workflows/ci.yml/badge.svg)](https://github.com/ryderderder/teamctl/actions/workflows/ci.yml)

**teamctl** turns a tmux window into an AI agent team: a *lead* agent (or you)
in the left pane manages *teammates* — Claude Code, Codex, or Grok CLI
sessions — as tmux panes tiled in a square grid to the right. It spawns
interactive teammates, dispatches headless tasks and reads their results back
as JSON, routes work to whichever provider is currently available, tracks real
usage where providers expose it, and tears teammates down cleanly
(process-tree-verified, no orphans). Single-file Python, stdlib only.

## Requirements

| platform | status |
| --- | --- |
| macOS | supported — developed and verified here |
| Linux | supported — verified by CI (ubuntu-latest, live tmux pane tests) |
| Windows | native: **not supported** (tmux doesn't run there). Use WSL — the installer detects native Windows and prints the WSL steps. |

- [tmux](https://github.com/tmux/tmux) (teamctl runs inside a tmux session)
- Python 3.11+ (3.9+ works, but config-file support needs `tomllib` from 3.11)
- At least one provider CLI installed and logged in:
  [Claude Code](https://code.claude.com) (`claude`), OpenAI Codex CLI
  (`codex`), or Grok CLI (`grok`)

The installer detects missing tmux/python3 and **offers** to install them via
your package manager (brew / apt-get / dnf / pacman) — it always asks first,
tells you when a command will use sudo, and `--no-deps` skips the offers
entirely. Provider CLIs are never auto-installed; their official install
one-liners are printed instead.

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

### Install via your AI agent — paste this prompt

Prefer to have an agent set everything up? Paste this into Claude Code,
Codex, or Grok (also in [INSTALL_PROMPT.md](INSTALL_PROMPT.md)):

```text
Install teamctl (https://github.com/ryderderder/teamctl) for me — it manages
AI teammates (Claude Code / Codex / Grok CLIs) as tmux panes. Do all of the
following, in order:

1. Run the installer:
     curl -fsSL https://raw.githubusercontent.com/ryderderder/teamctl/main/install.sh | bash
   If it reports missing dependencies (tmux, or python3 older than 3.11),
   install them with the system package manager (ask me before anything
   that needs sudo). If it reports no provider CLI, show me the official
   install one-liners it prints and ask which (if any) to run.
   Make sure ~/.local/bin is on my PATH; fix my shell profile if not.

2. Configure it: run `teamctl init` interactively if you have a terminal
   for me to answer prompts; otherwise run `teamctl init --yes` and tell me
   I can re-run `teamctl init` or use `teamctl config --menu` later.

3. Offer me lead mode: explain that `teamctl lead on` installs a
   lead-agent identity for Claude Code (a skill, a CLAUDE.md block, and a
   recommended per-prompt reminder hook — all reversible with
   `teamctl lead off`), then run it if I say yes.

4. Verify your work: run `teamctl --version` and `teamctl providers`, and
   show me the output.

5. Report what you did, what you skipped and why, and finish by telling me
   my controls:
     - from the shell: `teamctl config --menu` to adjust preferences,
       `teamctl lead on|off|status` for the lead identity,
       `./uninstall.sh` (or `teamctl lead off` first) to undo everything.
     - from a chat: with lead mode on, I can just say "open the teamctl
       menu" to any lead agent and it will present and apply my settings.
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
each further teammate splits the largest non-lead pane (teamctl-spawned or
not) in whichever direction keeps panes square-ish, so four teammates form a
2×2 grid beside the lead. The lead pane is never re-split, never loses focus
to a spawn, and keeps its configured share of the window width
(`[layout] lead_width`, default 50%) across spawns and shutdowns.

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

### Lead-agent playbook

If your lead is itself an AI agent (Claude Code, Codex, Grok, …), give it
these standing rules. **For Claude Code, `teamctl lead on` automates the
paste-in** (see [Lead mode](#lead-mode) below); for other CLIs, paste them
into the agent's instructions file (`AGENTS.md` or equivalent):

```
Before spinning up a teammate, planning a multi-agent effort, or dispatching
anything large:
1. Run `teamctl usage` — real usage %/reset times where the provider exposes
   them (it also refreshes availability signals as a side effect).
2. Run `teamctl providers` — which subscriptions are installed, authed, and
   not currently exhausted (exhaustion signals auto-expire at reset time).
3. Decide the provider from that live data plus task fit — or use
   `teamctl route` to auto-pick and dispatch in one step. Capacity changes
   hour to hour; don't hard-code a choice.
4. For a live interactive teammate you can also send `/usage` into its pane
   (`teamctl send <role> "/usage"`, then tmux capture-pane) to read that
   provider's own account numbers.
5. Match model and effort to the task — light/cheap for mechanical work,
   heavyweight for hard reasoning — via --model/--effort, honoring the
   user's configured defaults. Shut every teammate down
   (`teamctl shutdown <role>`) the moment its job is done.
```

## Lead mode

`teamctl lead on` installs a durable *manager identity* for a Claude Code
lead agent — the standing rules from the playbook above (stay responsive,
delegate non-trivial work, decide capacity from `teamctl usage`/`providers`
live data, one owner per file, zero idle teammates, the user always
overrides) — in three tiers, from discoverable to unmissable:

1. **Skill** (`~/.claude/skills/teamctl-lead/SKILL.md`) — *discoverable*.
   Claude Code loads it whenever delegation, teammates, multi-agent
   planning, or capacity questions come up.
2. **CLAUDE.md block** — *always on*. A compact, marker-guarded block
   (`<!-- BEGIN teamctl-lead -->` … `<!-- END teamctl-lead -->`) appended to
   `~/.claude/CLAUDE.md`, in context from the first prompt of every session.
3. **Hook** (recommended; asked as Y/n — default **yes** — or forced with
   `teamctl lead on --hook`) — *per-prompt, the strongest tier*. A
   `UserPromptSubmit` hook in `~/.claude/settings.json` that `echo`es a
   one-line reminder; its stdout is injected into context on **every**
   prompt, so it always fires and keeps working even after context
   compaction has dropped the CLAUDE.md text from a long session. That is
   why it's the recommended tier.

Every step is skipped if already present, backed up first if it changes an
existing file, and printed with its exact revert. `teamctl lead on` refuses
to touch a `settings.json` it cannot parse.

**The off switch:** `teamctl lead off` removes exactly what `on` installed —
the skill directory, the marker block (your other CLAUDE.md content is
preserved byte-for-byte), and the teamctl-lead hook entry (other hooks and
settings keys untouched) — each with a fresh backup, tolerating partial
installs, and reports what it removed and what it left alone.
`teamctl lead status` shows per-tier state at any time.

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

[layout]
lead_width = 50             # lead pane's share of the window width, in %
                            # (clamped 20-80; try 33 for a wider team area)
```

The lead pane's width is re-pinned to `lead_width` after every spawn and
shutdown, so re-tiling never eats your main pane. New teammates fold into
the right-hand grid by splitting the largest non-lead pane in the window —
including panes teamctl didn't create — instead of carving slivers off the
lead.

Command-line `--model` / `--effort` always override the config. State lives
in `~/.local/state/agent-team/state.json` (override with `$TEAMCTL_STATE`).

### Adjusting preferences

You never need to edit the TOML by hand:

```sh
teamctl config                                  # show current settings as dotted keys
teamctl config providers.claude.model           # show one value
teamctl config providers.claude.model sonnet    # set one key (others preserved)
teamctl config routing.preference "codex,claude"  # comma-separated -> list
teamctl config --menu                           # numbered menu: pick, edit, repeat
```

Or from a chat: with [lead mode](#lead-mode) on, tell your lead agent
*"open the teamctl menu"* — the teamctl-lead skill teaches it to read your
settings with `teamctl config`, present them as a numbered menu in chat,
and apply your changes key by key.

Sets rewrite the file safely: the previous version is backed up to
`config.toml.bak-teamctl`, all other keys are preserved, and a config that
fails to parse is refused rather than silently replaced. You can also just
re-run `teamctl init` any time to redo the whole wizard.

`teamctl init` also offers (default **no**, backups made first):

- a marker-guarded block in `~/.tmux.conf` for the pane-border and status-bar
  `role · model` labels;
- installing `claude-statusline` (shows `model · effort · ctx N%` in Claude
  Code) and adding the `statusLine` key to `~/.claude/settings.json` — skipped
  if a `statusLine` key already exists. The statusline also caches the
  rate-limit numbers Claude Code pipes to it (documented statusLine JSON:
  `rate_limits.five_hour/seven_day` — subscribers only), which is what powers
  `teamctl usage`'s Claude column;
- installing [lead mode](#lead-mode) for Claude Code (same as
  `teamctl lead on`).

## Uninstall

```sh
./uninstall.sh
```

Removes the binaries, removes the tmux marker block (backup made first), and
removes the `statusLine` settings key if — and only if — it points at this
tool's script (backup made first). Config and state files are left in place;
the script prints the one-liner to remove them too.

If you installed [lead mode](#lead-mode), run `teamctl lead off` **before**
uninstalling (the uninstaller removes the `teamctl` binary itself).

## Security

An agent *team* only works hands-off, which in practice means running the
provider CLIs in their autonomous modes (Claude Code
`bypassPermissions`/`--dangerously-skip-permissions`, Codex's `--yolo`/
full-access sandbox settings, Grok's auto-approve). **teamctl itself never
sets those flags** — each teammate launches with whatever permission posture
you have configured for that CLI — but if your defaults are autonomous,
every teammate is too. All three vendors document autonomous modes as
intended for isolated environments and warn about prompt injection and
credential exposure on bare hosts. Run agent teams inside a container/VM
where possible, and at minimum only against repositories and inputs you
trust:

- Claude Code: <https://code.claude.com/docs/en/security>
- Codex CLI: <https://developers.openai.com/codex/security>
- Grok CLI: <https://docs.x.ai/build/overview>

Also remember `teamctl send` types raw keys into a live agent's terminal —
anything (or anyone) able to run teamctl can steer every teammate.

## Limitations (honest ones)

- **Usage numbers exist only where providers expose them locally.** Codex
  writes rate-limit windows to its session logs, so `teamctl usage` shows real
  percentages and reset times for it. Claude's 5h/weekly numbers come from
  the statusline cache (Claude Code pipes documented `rate_limits` fields to
  the status line for subscribers; ours saves them) — so they exist only
  after a Claude Code turn has run with the teamctl statusline installed,
  and `teamctl usage` labels the cache's age. Grok exposes nothing locally,
  and `teamctl usage` says so rather than inventing numbers.
- **Some parsed provider formats are observed, not documented.** Grok's JSON
  output shape (`{text, stopReason, sessionId, …}`) and the location/format
  of Codex's session-log rate-limit events are reverse-engineered from real
  output. teamctl parses both defensively and degrades to "usage unknown" /
  raw text instead of failing — but re-verify after provider CLI upgrades.
  (Claude's statusline fields and `codex exec resume` are documented.)
- **`followup` for Codex resumes the most recent session** (`codex exec
  resume --last`): with several concurrent codex teammates the wrong session
  could be resumed. Codex documents id-addressed resume (`codex exec resume
  <SESSION_ID>`), but capturing the id per dispatch would require its
  `--json` event stream, which changes the captured result shape — so
  teamctl doesn't do it yet. Keep concurrent codex followups serialized.
- **Exhaustion signals are best-effort.** `route` skips a provider only after
  its output was seen to contain a limit/auth error, or Codex's own log shows
  100% on the 5h window; signals with a known reset time auto-expire.
- **`#()` in tmux formats is not portable** — some tmux builds don't execute
  shell commands in status formats at all. That's why the pane labels use
  `@role`/`@model` user options instead. No shell runs in your status bar.
- **`send` types into a terminal.** It sends literal keys plus Enter; there's
  no acknowledgment protocol. For machine-readable round-trips use
  `dispatch`/`result`.
- **macOS/Linux only** (uses `flock`, `pgrep`, POSIX signals): macOS verified
  directly, Linux verified by CI. Native Windows can't work (no tmux); WSL
  provides a standard Linux userland and is the supported route there, but
  hasn't been separately tested.
- Provider CLIs must already be installed and logged in; teamctl never
  handles credentials itself.

## License

MIT — see [LICENSE](LICENSE).
