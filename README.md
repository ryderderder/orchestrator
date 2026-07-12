# teamctl

**teamctl** turns a tmux window into an AI agent team: a *lead* agent (or you)
in the left pane manages *teammates* — Claude Code, Codex, or Grok CLI
sessions — as tmux panes tiled in a square grid to the right. It spawns
interactive teammates, dispatches headless tasks and reads their results back
as JSON, routes work to whichever provider is currently available, tracks real
usage where providers expose it, and tears teammates down cleanly
(process-tree-verified, no orphans). Single-file Python, stdlib only.

## Install

```sh
curl -fsSL https://raw.githubusercontent.com/ryderderder/teamctl/main/install.sh | bash
```

That one line is the whole setup: the installer copies the tools to
`~/.local/bin`, offers to install anything missing (tmux — a hard
requirement — defaults to yes; nothing is ever installed without asking),
then drops you into a tmux session where the zero-question **express
setup** has already run — providers detected, sane defaults written, a
compact summary of what was chosen, done in seconds. Want to pick models,
routing order, and integrations yourself? `bash -s -- --custom-init` runs
the rich arrow-key wizard instead, and `teamctl init --custom` opens it
any time later. Other opt-outs: `--no-init` (skip the setup/tmux
bootstrap), `--no-deps` (skip dependency offers). Safe to re-run. From a
checkout:
`git clone https://github.com/ryderderder/teamctl && cd teamctl && ./install.sh`.

<!-- install.gif lands with the v0.3.0 install-flow re-record (see docs/recordings/README.md):
![Install: the one-liner installs teamctl, detects dependencies and provider CLIs, then drops you into a tmux session with the express setup already done](docs/assets/install.gif)
-->

Here is the lead-and-teammates workflow — check real usage, see `route` pick a
provider, spawn and dispatch teammates as labeled tmux panes, read a result
back, and tear everything down cleanly (recorded with the token-free `shell`
provider and neutral model labels; the mechanics are identical for real
providers):

![Demo: a lead tmux pane runs teamctl usage and route --dry-run, spawns code-reviewer and researcher panes and dispatches an analyst task, each pane labeled with its role and model, then reads the analyst's JSON result back with result --wait and shuts all three down, ending with an empty teammate list](docs/assets/demo.gif)

### Install via your AI agent — paste this prompt

Prefer to have an agent set everything up? Paste this into any AI coding
CLI (also in [INSTALL_PROMPT.md](INSTALL_PROMPT.md)):

```text
Install teamctl (https://github.com/ryderderder/teamctl) for me — it manages
AI teammates (Claude Code / Codex / Grok CLIs) as tmux panes. Do all of the
following, in order:

1. Run the installer:
     curl -fsSL https://raw.githubusercontent.com/ryderderder/teamctl/main/install.sh | bash -s -- --no-init
   (--no-init because you are driving the setup yourself; without it the
   installer enters tmux and runs the express setup). If it reports missing
   dependencies (tmux, or python3 older than 3.11), install them with the
   system package manager (ask me before anything that needs sudo). If it
   reports no provider CLI, show me the official install one-liners it
   prints and ask which (if any) to run. Make sure ~/.local/bin is on my
   PATH; fix my shell profile if not.

2. Configure it: run `teamctl init` (the express setup — zero questions;
   it detects providers, writes sane defaults, and prints a compact
   summary). Show me that summary, and tell me I can run
   `teamctl init --custom` (rich arrow-key wizard) or
   `teamctl config --menu` any time to change it. Express uses the
   detected provider order for routing; if I want a different order, set
   it with `teamctl config routing.preference ...` — never pick it for me.

3. Offer me lead mode: explain that `teamctl lead on` installs a manager
   identity into every detected agent CLI's global instructions file
   (plus a skill and a recommended per-prompt reminder hook for Claude
   Code — mechanisms the other CLIs don't have), all reversible with
   `teamctl lead off`. Run it if I say yes.

4. Verify your work: run `teamctl --version`, `teamctl providers`, and
   `teamctl models`, and show me the output.

5. Report what you did, what you skipped and why, and finish by telling me
   my controls:
     - from the shell: `teamctl config --menu` to adjust preferences,
       `teamctl lead on|off|status` for the lead identity,
       `./uninstall.sh` (or `teamctl lead off` first) to undo everything.
     - from a chat: with lead mode on, I can just say "open the teamctl
       menu" to any lead agent and it will present and apply my settings.
```

[![ci](https://github.com/ryderderder/teamctl/actions/workflows/ci.yml/badge.svg)](https://github.com/ryderderder/teamctl/actions/workflows/ci.yml)

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
your package manager (brew / apt-get / dnf / pacman) — it always asks first
(tmux defaults to yes, everything else to no), tells you when a command will
use sudo, and `--no-deps` skips the offers entirely. Provider CLIs are never
auto-installed; their official install one-liners are printed instead.

## Quickstart

```sh
# Interactive teammate: opens a provider CLI pane seeded with a prompt.
teamctl spawn reviewer --provider codex \
    --prompt "Review the diff on this branch for correctness."

# See who's active.
teamctl list

# Type a follow-up instruction into a running teammate's pane.
teamctl send reviewer "Focus on the error handling in server.py."

# Headless task: runs in a watchable pane, result lands in a handoff dir.
teamctl dispatch researcher --provider grok \
    --task "Summarize the TODOs in this repo as JSON." --cwd ~/myproject

# Read the result back (blocks until done; fails fast if the teammate dies).
teamctl result researcher --wait

# Another turn in the same provider session.
teamctl followup researcher --task "Now rank them by effort."

# No --provider? Your configured routing order decides (or the only
# detected provider). With several providers and no configured order,
# teamctl asks rather than silently picking one for you.
teamctl spawn helper --prompt "Draft release notes from the last 10 commits."

# Or let route pick: first *available* provider in your configured order,
# skipping anything not installed, not logged in, or known-exhausted.
teamctl route helper --task "Draft release notes from the last 10 commits."
teamctl route helper --task "..." --dry-run     # preview the choice + command

# Provider availability, real usage, and current model lists.
teamctl providers
teamctl usage
teamctl models

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
`result.json`, stderr goes straight to `error.log` (durably — a background
tail mirrors it into the pane so the run stays watchable), and an exit
`status` file makes `result --wait` reliable — including failing fast when
a teammate dies without reporting, and recording the killing signal
(`DONE 137 SIGKILL`) when one is killed. A dispatched teammate's pane
closes by itself when the task finishes; the teammate stays tracked as
`done` (`teamctl list` shows lifecycle state), `result` keeps working
indefinitely, `followup` continues the same provider session in a fresh
pane, and `shutdown` clears the state and handoff artifacts when you're
finished with the role.

### Lead-agent playbook

If your lead is itself an AI agent, give it these standing rules.
**`teamctl lead on` automates the paste-in for every detected CLI** (see
[Lead mode](#lead-mode) below); for anything else, paste them into the
agent's instructions file:

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

`teamctl lead on` installs a durable *manager identity* for your lead
agent — the standing rules from the playbook above (stay responsive,
delegate non-trivial work, decide capacity from `teamctl usage`/`providers`
live data, one owner per file, zero idle teammates, the user always
overrides) — into **every detected CLI** (or one, with
`--cli claude|codex|grok|all`):

1. **Instructions block** — *always on; all three CLIs*. A compact,
   marker-guarded block (`<!-- BEGIN teamctl-lead -->` …
   `<!-- END teamctl-lead -->`) appended to each CLI's documented global
   instructions file: `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`,
   `~/.grok/AGENTS.md`. In context from the first prompt of every session;
   re-running `lead on` refreshes a stale block in place (backup first).
2. **Skill** (`~/.claude/skills/teamctl-lead/SKILL.md`) — *discoverable;
   Claude Code only*. Loaded whenever delegation, teammates, multi-agent
   planning, or capacity questions come up. It also teaches the chat-based
   settings menu ("open the teamctl menu").
3. **Hook** (recommended; asked as Y/n — default **yes** — or forced with
   `teamctl lead on --hook`) — *per-prompt, the strongest tier; Claude Code
   only*. A `UserPromptSubmit` hook in `~/.claude/settings.json` that
   `echo`es a one-line reminder; its stdout is injected into context on
   **every** prompt, so it always fires and keeps working even after
   context compaction has dropped instruction-file text from a long
   session. That is why it's the recommended tier.

Skills and hooks are Claude Code mechanisms with no Codex/Grok equivalent —
tiers 2 and 3 being Claude-only is parity with what each CLI offers, not a
preference. Every step is skipped if already present, backed up first if it
changes an existing file, and printed with its exact revert. `teamctl lead
on` refuses to touch a `settings.json` it cannot parse.

### Delegation posture

How eagerly should a lead agent hand work to teammates? Choose once —
`[lead] delegation` in the config, asked by the wizard, shown by
`teamctl lead status`:

- **ask** (default): the first time non-trivial work comes up in a
  session, the lead asks plainly whether to use agent teams for work like
  it (parallel teammates; taps your other AI subscriptions and resources)
  — and offers to remember your answer
  (`teamctl config lead.delegation always|manual`). Once, then never
  again that session.
- **always**: the lead delegates non-trivial work by default.
- **manual**: single-agent work unless you explicitly ask for a team.

Whatever the posture — including manual — a genuinely large task
(multi-file, parallelizable, long-running) earns one, and only one,
"this is big — want me to spin up a team?" suggestion per session; a no
is final. The per-prompt hook echoes the live posture
(`delegation=<value>`) on every prompt, so the lead knows the current
mode even after context compaction.

**The off switch:** `teamctl lead off` removes exactly what `on` installed —
the skill directory, each CLI's marker block (your surrounding content is
preserved byte-for-byte), and the teamctl-lead hook entry (other hooks and
settings keys untouched) — each with a fresh backup, tolerating partial
installs, and reports what it removed and what it left alone.
`teamctl lead status` shows per-tier, per-CLI state at any time.

## Configuration

> **`teamctl init` is a twelve-line dark room that finds your providers and
> locks sane defaults; `--custom` is a three-screen cockpit if you want to
> aim.**

Three ways in, same config file every way (canonical design:
[docs/design/installer-spec.md](docs/design/installer-spec.md)):

- **`teamctl init` — express (the default).** Zero questions: detects your
  provider CLIs (`ready` / `quiet` / `locked out`), locks sane defaults
  (each CLI's own model, effort `high`, routing in alphabetical order,
  delegation `ask`, voice `normal`), writes the config, and prints one
  compact frame. Done in seconds; `--yes` keeps its scripted contract
  (same writes, no chrome).
- **`teamctl init --custom` — the cockpit.** A three-screen arrow-key
  terminal UI (stdlib curses, 256-color, designed for a 100×30 tmux
  pane): **models** (per-provider picks from live discovery, plus a
  `custom…` escape hatch — ids always pass through verbatim), **posture**
  (effort, voice, delegation with one-line glosses, and the routing order
  reorderable in place with `h`/`l`), and **seal** (a review strip, the
  optional integrations as off-by-default toggles, and a single
  `write config` action). `q` quits without writing; `p` drops to the
  plain path.
- **The plain path.** Wherever the cockpit can't run — no tty, dumb TERM,
  `TEAMCTL_UI=plain`, or you pressed `p` — a handful of short prompts
  with the express defaults on blank. No integration questions (those
  live on the seal screen and in `teamctl lead on`;
  `TEAMCTL_INIT_EXTRAS=1` re-enables them for scripted power users).

`~/.config/agent-team/config.toml`:

```toml
[output]
verbosity = "normal"        # terse | normal | detailed

[lead]
delegation = "ask"          # ask | always | manual — how eagerly a lead
                            # agent hands work to teammates (see Lead mode)

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
preference = ["codex", "claude"]  # YOUR order — express uses the detected
                            # order; the custom wizard asks for it.
                            # `route` picks the first available entry, and
                            # a bare spawn/dispatch (no --provider) uses the
                            # first entry. Without a configured preference
                            # the fallback order is alphabetical — arbitrary,
                            # not a recommendation — and several providers
                            # with no preference means spawn/dispatch ask
                            # rather than silently choosing.

[usage]
probe_stale_minutes = 30    # `usage` flags probe/statusline data older
                            # than this many minutes as stale

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
teamctl config --menu                           # arrow-key settings editor
```

`config --menu` uses the same rich curses UI as the custom wizard —
arrow keys move, Left/Right cycles known values (delegation, verbosity,
routing order), Enter edits anything as text, `s` saves (with a backup).
On a terminal that can't run it, the numbered pick-a-setting menu appears
instead.

Or from a chat: with [lead mode](#lead-mode) on, tell your lead agent
*"open the teamctl menu"* — the teamctl-lead skill teaches it to read your
settings with `teamctl config`, present them as a numbered menu in chat,
and apply your changes key by key.

### Models

Model ids pass through to the provider CLI **verbatim** — teamctl carries
no model list, so new models work the day a provider ships them, with no
teamctl update. `teamctl models [provider]` is best-effort discovery for
convenience only: grok's documented `grok models` output is passed
through; Codex's local models cache (`~/.codex/models_cache.json` — an
observed file, parsed defensively) lists slugs and supported efforts; for
Claude, which has no listing command, the documented aliases are noted.
The wizard shows the same discovery as suggestions but accepts any id.

### Fresh usage numbers: hidden probes

`teamctl usage --probe [provider|all]` opens a provider's own TUI in a
detached background tmux session (`teamctl-probe` — never a pane in your
window), waits for it to settle, types the provider's own usage command
(grok `/usage`, codex `/status`), scrapes the numbers, and tears the TUI
down with the same process-tree-verified kill used for teammates. Results
are cached with a timestamp; plain `teamctl usage` reports them alongside
the log/statusline-derived data, labels their age, and flags anything
older than `[usage] probe_stale_minutes` (default 30) as stale. Claude is
not probed: its statusline cache is the documented, cheaper source.
Probing is always explicit — teamctl never opens a provider session on its
own. OBSERVED (not vendor-documented): the usage commands are local UI
commands and no token spend was observed, but opening a TUI does start a
provider session.

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
- installing [lead mode](#lead-mode) for your detected agent CLIs (same as
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
  output shape (`{text, stopReason, sessionId, …}`), the location/format of
  Codex's session-log rate-limit events, Codex's models cache, and the TUI
  text scraped by `usage --probe` (grok `/usage`, codex `/status` — the
  latter explicitly unstable upstream) are reverse-engineered from real
  output. teamctl parses them all defensively and degrades to "usage
  unknown" / "probe failed" / raw text instead of crashing — but re-verify
  after provider CLI upgrades. (Claude's statusline fields, `codex exec
  resume`, and `grok models` are documented.)
- **Follow-ups are exact-session on all providers.** `followup` resumes
  the specific captured session id (claude `--resume <id>`, grok `-r <id>`,
  codex `exec resume <id>` — all verified against each CLI's help) and
  refuses rather than guessing "most recent" when no id was captured.
  The codex id comes from an observed stderr banner (`session id: <uuid>`),
  with the rollout-log filename as a fallback — re-verify after codex
  upgrades. claude/grok ids come from their JSON results.
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
  handles credentials itself. **Login detection is heuristic**: it infers
  login from observed artifacts (`~/.claude.json`, `~/.codex/auth.json`,
  `~/.grok/auth.json` — with signs-of-CLI-use as grok's last-resort
  fallback, never bare directory existence). A CLI update that moves them
  shows up as "not-authed"; the CLIs themselves stay the source of truth.

## Credits

teamctl was inspired by Claude Code's experimental
[agent teams](https://code.claude.com/docs/en/agent-teams) feature — the
lead-and-teammates shape, reimagined on plain tmux so that any provider's
CLI can play on equal footing.

## License

MIT — see [LICENSE](LICENSE).
