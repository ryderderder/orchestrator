# teamctl

**teamctl** turns a tmux window into an AI agent team: a *lead* agent (or you)
in the left pane manages *teammates* — Claude Code, Codex, Grok, or Gemini
CLI sessions, or any CLI you teach it via a custom-provider block — as tmux
panes tiled in a square grid to the right. It spawns interactive teammates,
dispatches headless tasks and reads their results back as JSON, gives every
teammate its own **git worktree** (parallel writers physically cannot
collide) with a one-command **land** step to merge the work back, routes
work to the subscription with the **most quota left**, detects which
teammate is busy / blocked on an approval / idle, resurrects the roster
after a reboot, and tears teammates down cleanly (process-tree-verified, no
orphans, no stranded work). Single-file Python, stdlib only.

## Install

**Tell your agent to install it — paste this** into any AI coding CLI
(also in [docs/INSTALL_PROMPT.md](docs/INSTALL_PROMPT.md)):

```text
Install teamctl for me — https://github.com/ryderderder/teamctl
(it runs AI teammates — Claude Code / Codex / Grok / Gemini CLIs — as tmux panes).

1. Orient first — read these from the repo (main branch):
   README.md · docs/AGENT_GUIDE.md · llms.txt
2. Install:
   curl -fsSL https://raw.githubusercontent.com/ryderderder/teamctl/main/install.sh | bash -s -- --no-init
   Essentials: ask me before anything that needs sudo; never install a
   provider CLI without asking; make sure ~/.local/bin is on my PATH.
3. Configure: run `teamctl init` (zero questions) and show me its summary.
4. Verify: run `teamctl doctor` and show me the output.
5. Tell me my controls: `teamctl settings` · `teamctl lead on|off|status` ·
   `teamctl uninstall` (run `teamctl lead off` first).
```

Or run the one-liner yourself:

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

[![ci](https://github.com/ryderderder/teamctl/actions/workflows/ci.yml/badge.svg)](https://github.com/ryderderder/teamctl/actions/workflows/ci.yml)

## What's new in v0.5.0

**More providers, safer parallelism, smarter routing** — and four
behavior changes worth knowing before you upgrade:

1. **Routing picks by headroom now.** `route` (and provider defaults)
   rank the *usable* providers by remaining quota instead of strict list
   order — your preference order only breaks ties. Nothing previously
   excluded can ever be selected; only the order among survivors changes.
   Want the old behavior? One line: `teamctl config routing.strategy
   preference`.
2. **Worktree isolation is ON by default.** `spawn`/`dispatch`/`route`
   inside a git repo now give the teammate its own branch
   (`teamctl/<role>`) in its own worktree under the state dir. Opt out
   per-launch with `--no-worktree` or globally with `teamctl config
   worktree.enabled false`. Outside a git repo nothing changes (one
   honest note, plain cwd). Disk note: a worktree is a full checkout of
   *tracked* files; untracked artifacts (node_modules, venvs, build
   dirs) are per-worktree by design. See
   [Worktrees & landing](#worktrees--landing-parallel-writers-that-cannot-collide).
3. **Gemini CLI is a first-class provider** — spawn, headless dispatch,
   exact-session follow-ups (`--resume <captured-uuid>`), auth
   detection, lead-mode block in `~/.gemini/GEMINI.md`. Two honest
   caveats: Gemini exposes **no local usage feed**, so it shows as
   `quiet` forever (routing treats it as 0% used); and upstream issue
   #24808 means a resume can intermittently fail — the failure lands
   verbatim in `error.log` and is re-triable.
4. **Bring your own CLI**: a `[providers.custom.*]` config block teaches
   teamctl any provider that speaks `<cmd> [flags] "<prompt>"` — no code
   changes. See [Custom providers](#custom-providers-bring-your-own-cli).

Also new: `teamctl status` (busy / needs-input / idle per teammate, with
a `[notify]` hook on transitions — env vars `TEAMCTL_ROLE` /
`TEAMCTL_MATE_STATE` / `TEAMCTL_PREV_STATE`), `teamctl land` /
`teamctl worktree list|prune`, `teamctl resurrect` (the roster survives
reboots), a doctor `environment` row (including WSL awareness), and
`--json` on every new surface.

## Updating

```sh
teamctl update --check     # installed vs latest, from your install source
teamctl update             # replace ~/.local/bin/teamctl
```

The installer records where teamctl came from (`install-meta.json` in the
state dir: a git clone, the curl one-liner, or a plain local copy).
`update` re-fetches from that source and atomically replaces the
installed copies: git checkouts fetch and read the files out of
`FETCH_HEAD` (your checkout is never moved or dirtied), private repos go
through an authenticated `gh`, public installs through curl. Your config
(`~/.config/agent-team/`) and state are never touched. An unreachable
source prints the reason per route — never a stack trace — and a download
that doesn't compile is refused.

teamctl also runs a **background version check** at most once a day
(fully detached, silent on any failure, never blocking a command). When a
newer version is known, one dim line appears at session start and under
`providers`/`usage`:

    · teamctl X.Y.Z available — teamctl update

Tune it in the config under `[update]`: `check = true|false` and
`mode = "prompt" | "auto" | "off"` — `auto` applies a known-newer version
at session start (an explicit opt-in; never the default), `off` never
mentions updates. Installs made before v0.4.0 have no recorded source:
re-run `install.sh` once and `teamctl update` works from then on.

## Health check

```sh
teamctl doctor
```

A one-shot environment check in the dark-room style — a `ok` / `warn` /
`fail` row per concern: the environment itself (WSL is recognized and
greeted as supported, with a browser-sign-in interop note), python
version, tmux (presence + version quirks), the
[provider states](#provider-states), config parse + schema sanity, the
Claude Code statusline wiring, whether the install-source metadata is
recorded (so `teamctl update` works), a writable state dir, orphaned
worktrees, and crash-lost teammates waiting for `teamctl resurrect`. The
exit code reflects the worst finding (`0` ok · `1` warn · `2` fail), so
it drops into CI or a pre-flight script.

## Provider states

Every surface that names a provider — `teamctl providers`, `teamctl
usage`, the init frames, the installer's detection screen — speaks the
same word lattice, so different truths never share one ambiguous label:

| state | meaning | what to do |
|---|---|---|
| `ready` | installed, signed in, usage numbers known (shown inline) | nothing — spawn away |
| `quiet` | installed and signed in; no usage numbers seen yet | nothing — it wakes on first use (each surface shows the exact wake hint) |
| `locked out` | installed but not signed in | the CLI's own login: `claude auth login` / `codex login` / `grok login` / gemini's in-TUI `/auth` |
| `not installed` | CLI not on PATH | the installer prints the official install one-liners |
| `unknown` | auth artifacts exist but can't be read | reported honestly instead of guessing — check the CLI |

`quiet` and `ready` providers are equally usable for spawning and
routing — usage data changes the word, not the eligibility. (Gemini is
the permanent-`quiet` case: it exposes no local usage feed at all, and
teamctl says so instead of inventing numbers.) A custom provider with no
auth configuration shows `quiet — auth not probed` and stays routable.
Residual usage artifacts left by an *uninstalled* CLI (e.g. leftover
`~/.codex/sessions` rollouts) are flagged as `not installed — residual
usage history found` and never rendered as a live provider.

## Requirements

| platform | status |
| --- | --- |
| macOS | supported — developed and verified here |
| Linux | supported — verified by CI (ubuntu-latest, live tmux pane tests) |
| WSL | runs as Linux — the installer greets it as supported and `doctor` reports the environment (with a note about browser sign-ins through Windows interop). Detection is tested; WSL itself has not been separately field-verified. |
| Windows | native: **not supported** (tmux doesn't run there). Use WSL — the installer detects native Windows and prints the WSL steps. |

- [tmux](https://github.com/tmux/tmux) (teamctl runs inside a tmux session)
- Python 3.11+ (3.9+ works, but config-file support needs `tomllib` from 3.11)
- git, only if you use worktree isolation (on by default *in a git repo*;
  everything else works without git)
- At least one provider CLI installed and logged in:
  [Claude Code](https://code.claude.com) (`claude`), OpenAI Codex CLI
  (`codex`), Grok CLI (`grok`), or
  [Gemini CLI](https://geminicli.com) (`gemini`) — or your own via
  [`[providers.custom.*]`](#custom-providers-bring-your-own-cli)

The installer detects missing tmux/python3 and **offers** to install them via
your package manager (brew / apt-get / dnf / pacman) — it always asks first
(tmux defaults to yes, everything else to no), tells you when a command will
use sudo, and `--no-deps` skips the offers entirely. Provider CLIs are never
auto-installed; their official install one-liners are printed instead.

## The front door

```sh
teamctl        # ← just this
```

Type `teamctl` on its own in a terminal and you're in: it opens your
default chat provider as the **lead** — in the `teamctl` tmux session, with
lead mode enabled — the full team-lead experience in one word. The default
provider/model/effort come from your config (`[lead] chat_provider` /
`chat_model` / `chat_effort`, falling back to your routing preference or
the only signed-in provider); set them in `teamctl settings`. If nothing's
signed in, or the chosen provider is locked out, it says so and names the
fix — never a stack trace. Piped or in CI (no terminal), bare `teamctl`
prints usage as before.

## Quickstart

```sh
# Interactive teammate: opens a provider CLI pane seeded with a prompt.
teamctl spawn reviewer --provider codex \
    --prompt "Review the diff on this branch for correctness."

# See who's active — and who's busy, blocked on an approval, or idle.
teamctl list
teamctl status            # busy / needs-input / idle (--watch to poll)

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

# Or let route pick: the usable provider with the most quota left
# (your configured order breaks ties; anything not installed, not
# logged in, or known-exhausted is excluded first).
teamctl route helper --task "Draft release notes from the last 10 commits."
teamctl route helper --task "..." --dry-run     # preview: every % it used

# Provider availability, real usage, and current model lists.
teamctl providers
teamctl usage
teamctl models

# A writing teammate worked in its own worktree (the default in a git
# repo) — review and merge its branch back, then everything cleans up.
teamctl land reviewer --dry-run       # the plan: diffstat + counts
teamctl land reviewer                 # checkpoint (asks) → merge → cleanup

# Clean teardown: kills the whole process tree, verifies it, closes the pane.
# A worktree with un-landed work is KEPT and reported — never discarded.
teamctl shutdown reviewer
```

## Worktrees & landing: parallel writers that cannot collide

The "never two teammates edit the same file" rule used to be prompt
convention; v0.5.0 makes it **mechanical**. In a git repo, every teammate
gets its own branch (`teamctl/<role>`) checked out in its own worktree
under the state dir (`~/.local/state/agent-team/worktrees/…`) — one
shared object store, zero shared working files. `--no-worktree` opts a
launch out; `[worktree] enabled = false` opts out globally; outside a git
repo teamctl says so once and uses the plain cwd.

**Landing** closes the loop:

```sh
teamctl land <role> --dry-run   # diffstat, commit/dirty counts, target branch
teamctl land <role>             # checkpoint uncommitted work (asks first)
                                #   → merge --no-ff into your CHECKED-OUT
                                #     branch → remove worktree + branch
```

What `land` will never do: switch your branches (`--into` only *asserts*
the target), stash for you, auto-resolve conflicts (a conflicted merge is
aborted and reported, your tree left clean), or land uncommitted work
silently. It works even after the teammate is gone — a shutdown that
finds un-landed work **keeps** the worktree and prints the way out, and
the worktree registry survives reboots. `teamctl worktree list` audits
everything teamctl ever created; `worktree prune` removes only what
provably holds nothing (never a live teammate's, never unique work).
Under the hood teamctl only ever uses git's own *non-forced* commands
(`worktree remove`, `branch -d`) — git's refusals are the backstop, and a
test audits that no `-D`/`--force`/`--hard` ever appears.

## Routing: to the subscription with the most quota left

`route` has always excluded the unusable (not installed / locked out /
exhausted / auth-error). v0.5.0 changes how the *survivors* are ranked:
**headroom** — the provider with the most remaining quota wins, reading
the same sources `teamctl usage` shows (native feeds first, probe cache
second, the tighter of the 5h/weekly windows governs). No usage data
ranks as 0% used (a quiet provider is usually a genuinely idle one), with
your preference order breaking ties. The reason line shows every number
the choice used — unknowns as `?%`, stale probe data flagged:

    route: selected codex (headroom: codex 12% used < claude 63% < grok ?% ·
    preference tiebreak claude>codex>grok; skipped gemini: not installed)

`teamctl config routing.strategy preference` restores the strict-order
behavior, bit-for-bit.

## Status: who's busy, who's blocked, who's idle

```sh
teamctl status                 # one-shot table
teamctl status --watch         # poll; prints transitions until Ctrl-C
teamctl status --json          # for an agent lead
```

Interactive teammates are classified with two pane samples ~0.7s apart:
changing content = `busy`; stable content matching the provider's known
approval-dialog shapes = `needs-input` (the matched prompt line is shown
— this is the "which teammate is silently stuck on a y/n?" answer);
anything else = `idle`. An unrecognized TUI degrades to `idle` — never a
wrong strong claim. Dispatch teammates keep their derived lifecycle
states (`running` / `done` / `failed(rc)` / `died`). A `[notify]
command = "…"` in config runs on transitions observed by
`status`/`list`/`--watch` (no daemon — unwatched transitions don't fire;
that's stated, not hidden), with context in `TEAMCTL_ROLE`,
`TEAMCTL_MATE_STATE`, `TEAMCTL_PREV_STATE`.

## Resurrect: the roster survives reboots

A reboot (or crash, or an accidentally closed pane) used to silently
erase interactive teammates from the roster. Now `reconcile` records them
as **lost**, and:

```sh
teamctl resurrect --dry-run    # what was lost, what a rebuild would do
teamctl resurrect              # rebuild (asks once; --yes for scripts)
```

Interactive teammates respawn **fresh** with everything teamctl recorded
(provider, model, effort, cwd, prompt — and their worktree is reused when
it survived). Their opening prompt says, honestly, that prior
conversation context was *not* restored — teamctl never captured
interactive session ids and refuses to guess "the most recent session".
Dispatch teammates never needed resurrecting: their artifacts live on
disk, and `result`/`followup` keep working — exact-session — after any
reboot. Bare `teamctl`, `list`, and `doctor` all point out lost teammates;
nothing is ever auto-resurrected without consent.

## Custom providers: bring your own CLI

Gemini is defined through a provider-spec registry — and the same
substrate is yours in config. Any CLI that speaks
`<cmd> [flags] "<prompt>"` drops in with zero code changes:

```toml
[providers.custom.aider]
command       = "aider"                          # must be on PATH
headless_args = ["--message", "{task}", "--yes"] # {task} is required
model_args    = ["--model", "{model}"]           # optional
effort_args   = []                               # [] / absent = no effort
                                                 # control (--effort is
                                                 # dropped with a note)
resume_args   = []                               # [] = follow-ups refused
session_id_key   = ""                            # id key in a JSON result…
session_id_regex = ""                            # …or a regex over stderr,
                                                 # then stdout text
interactive_args = []                            # extra flags for spawn
auth_env      = "OPENAI_API_KEY"                 # positive-only signal
auth_files    = ["~/.aider/oauth.json"]          # enables signed-out/in
login_hint    = "aider --login"
probe_command = ""                               # its TUI usage command
waiting_patterns = []                            # approval-dialog regexes
routable      = true
```

Everything degrades honestly: no `headless_args` → dispatch refuses
(spawn-only provider); no resume/session source → `followup` refuses; no
auth config → the lattice says `quiet — auth not probed` and the provider
stays routable (you configured it on purpose). A malformed block is
skipped with one stderr warning and can never take the built-ins down;
custom names can't shadow built-ins. `{task}`/`{model}`/`{effort}`/
`{session_id}` substitute inside argv tokens — no shell ever sees them
unquoted. A worked real-world example (Google Antigravity's `agy`,
including its macOS-over-SSH auth caveat) lives in
[docs/AGENT_GUIDE.md](docs/AGENT_GUIDE.md#custom-providers-providerscustom).

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
`--cli claude|codex|grok|gemini|all`):

1. **Instructions block** — *always on; every CLI*. A compact,
   marker-guarded block (`<!-- BEGIN teamctl-lead -->` …
   `<!-- END teamctl-lead -->`) appended to each CLI's documented global
   instructions file: `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`,
   `~/.grok/AGENTS.md`, `~/.gemini/GEMINI.md`. In context from the first
   prompt of every session; re-running `lead on` refreshes a stale block
   in place (backup first).
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

Skills and hooks are Claude Code mechanisms with no equivalent elsewhere —
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
  provider CLIs (the [provider state lattice](#provider-states):
  `ready` / `quiet` / `locked out` / `not installed`), locks sane defaults
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
                            # Under the default headroom strategy this is
                            # the TIEBREAK; under strategy = "preference"
                            # it is the whole ranking. A bare
                            # spawn/dispatch (no --provider) uses the first
                            # entry; several providers with no preference
                            # means spawn/dispatch ask rather than
                            # silently choosing.
strategy = "headroom"       # headroom (most remaining quota wins) |
                            # preference (strict order — the pre-v0.5 rule)

[worktree]
enabled = true              # teammate worktree isolation in git repos
                            # (v0.5.0 default ON; --no-worktree per launch)
# dir = ""                  # "" = <state dir>/worktrees
# branch_prefix = "teamctl/"
cleanup = "auto"            # auto: remove provably-clean worktrees at
                            # shutdown; keep: never remove

[notify]
# command = "notify-send teamctl"  # run on observed status transitions;
                            # env: TEAMCTL_ROLE, TEAMCTL_MATE_STATE,
                            # TEAMCTL_PREV_STATE (argv via shlex — no shell)

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

**`teamctl settings`** is the human face: a re-runnable dark-room cockpit
(the same aesthetic as `init --custom`) over the whole config, grouped
into sections — default chat, routing order, posture, layout, updates, and
per-provider model/effort. ↑/↓ move, Space or ←/→ cycle a choice
(delegation, update mode, effort, booleans…), Enter free-edits anything,
`s` saves (atomic, with a backup), `q` quits with a dirty-state confirm.
Without a TTY it degrades to printing the current values plus the matching
`teamctl config` one-liner for each — the scriptable path spelled out.

For scripting or one-off tweaks, `teamctl config` is the direct path (and
never needs the TOML edited by hand):

```sh
teamctl config                                  # show current settings as dotted keys
teamctl config providers.claude.model           # show one value
teamctl config providers.claude.model sonnet    # set one key (others preserved)
teamctl config routing.preference "codex,claude"  # comma-separated -> list
teamctl settings                                # the full cockpit (or config --menu)
```

Or from a chat: with [lead mode](#lead-mode) on, tell your lead agent
*"open the teamctl menu"* — the teamctl-lead skill teaches it to read your
settings with `teamctl config`, present them as a numbered menu in chat,
and apply your changes key by key (and to point you at `teamctl settings`
for the full cockpit).

### Models

Model ids pass through to the provider CLI **verbatim** — teamctl carries
no model list, so new models work the day a provider ships them, with no
teamctl update. `teamctl models [provider]` is best-effort discovery for
convenience only: grok's documented `grok models` output is passed
through; Codex's local models cache (`~/.codex/models_cache.json` — an
observed file, parsed defensively) lists slugs and supported efforts; for
Claude and Gemini, which have no listing commands, the accepted id shapes
are noted (Claude's documented aliases; any Gemini model id via `-m`).
The wizard shows the same discovery as suggestions but accepts any id.
Gemini has no per-invocation effort flag — a `--effort` for it is dropped
with a one-line note, never silently, and the wizard never writes one.

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
- wiring Claude Code's `statusLine` in `~/.claude/settings.json` to
  `teamctl statusline` (shows `model · effort · ctx N%`) — skipped if a
  non-teamctl `statusLine` key already exists, and a pre-v0.4.0
  `claude-statusline` wiring is migrated automatically. The statusline
  also caches the rate-limit numbers Claude Code pipes to it (documented
  statusLine JSON: `rate_limits.five_hour/seven_day` — subscribers only),
  which is what powers `teamctl usage`'s Claude column;
- installing [lead mode](#lead-mode) for your detected agent CLIs (same as
  `teamctl lead on`).

## Uninstall

```sh
teamctl uninstall     # add --yes to skip the confirm
```

Removes the `teamctl` binary (and any pre-v0.4.0 `claude-statusline`
companion), the `~/.tmux.conf` marker block, the `statusLine` settings key
if — and only if — it points at teamctl, and the install/update metadata —
each with a backup first. Config and state files are left in place; the
one-liner to remove them too is printed.

If you installed [lead mode](#lead-mode), run `teamctl lead off` **before**
uninstalling (the uninstaller removes the `teamctl` binary itself, so it
can't reverse lead mode afterward).

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
  and `teamctl usage` labels the cache's age. Grok exposes nothing locally
  (the hidden probe fills it in on request); Gemini exposes nothing at all
  — `teamctl usage` says so rather than inventing numbers, and headroom
  routing honestly treats no-data as "probably idle" (0% used) with your
  preference order as the tiebreak.
- **Gemini resume has a known upstream flake.** Exact-session follow-ups
  use `gemini --resume <captured-uuid>`; upstream issue #24808 reports
  intermittent "Invalid session identifier" failures. When it happens the
  error lands verbatim in `error.log`/`status` and the followup is
  re-triable — never silent. Gemini sessions are also project-scoped:
  follow-ups run from the dispatch cwd (teamctl already guarantees this).
- **Worktrees cost disk and don't share untracked files.** A teammate's
  worktree is a full checkout of *tracked* files (shared object store);
  node_modules/venvs/build dirs must be re-created per worktree — that's
  inherent to the isolation. `teamctl worktree list` shows everything;
  `prune` reclaims what provably holds nothing.
- **Status detection reads TUI text.** The busy/needs-input/idle
  classifier samples pane content and matches OBSERVED approval-dialog
  shapes per provider (calibrated against real panes; an unrecognized TUI
  degrades to `idle`, never a wrong strong claim). Provider TUI redesigns
  can dull it until patterns are refreshed — `waiting_patterns` in a
  custom block tunes it per provider. And there's no daemon: the
  `[notify]` hook fires only on transitions something actually observed.
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
  codex `exec resume <id>`, gemini `--resume <uuid>` — all verified
  against each CLI) and refuses rather than guessing "most recent" when no
  id was captured. The codex id comes from an observed stderr banner
  (`session id: <uuid>`), with the rollout-log filename as a fallback —
  re-verify after codex upgrades. claude/grok/gemini ids come from their
  JSON results (gemini's error JSON arrives on stderr and is checked too).
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
  provides a standard Linux userland and is the supported route there —
  the installer and `doctor` recognize it explicitly — but the detection
  logic is unit-tested against faked fixtures, not field-tested on a real
  WSL box. One known WSL rough edge: provider browser sign-ins go through
  WSL→Windows interop; if a login stalls, copy the printed URL into a
  Windows browser yourself.
- Provider CLIs must already be installed and logged in; teamctl never
  handles credentials itself. **Login detection reads observed
  artifacts**, content-validated (never bare file existence): claude's
  `.credentials.json` / `oauthAccount` in `~/.claude.json` / the macOS
  Keychain item (attribute lookup only — the secret is never read);
  codex's `~/.codex/auth.json` tokens; grok's `~/.grok/auth.json`
  credential entries, with signs-of-CLI-use as grok's flagged last-resort
  fallback. Exported provider API keys count too. Each artifact was
  verified against a live signed-in install, but a CLI update that moves
  them shows up as `locked out` (and an unreadable artifact as
  `unknown`); the CLIs themselves stay the source of truth. Gemini's
  artifact is `~/.gemini/oauth_creds.json` (plus `GEMINI_API_KEY` /
  `GOOGLE_API_KEY`); custom providers use whatever `auth_files` /
  `auth_env` you configure — and with neither, teamctl says "auth not
  probed" instead of guessing.

## Credits

teamctl was inspired by Claude Code's experimental
[agent teams](https://code.claude.com/docs/en/agent-teams) feature — the
lead-and-teammates shape, reimagined on plain tmux so that any provider's
CLI can play on equal footing.

## License

MIT — see [LICENSE](LICENSE).
