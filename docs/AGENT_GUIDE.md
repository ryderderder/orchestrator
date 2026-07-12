# teamctl — agent operating guide

Canonical machine-oriented reference for AI agents driving teamctl.
Humans should read the [README](../README.md) and
[use-cases](use-cases.md) instead; this file trades warmth for precision.

> Scope: v0.5.0. Synopses match `teamctl <cmd> --help` at the v0.5.0 tag.

## 1. Invariants (read first)

- teamctl runs **inside a tmux session**. Commands that create panes
  (`spawn`, `dispatch`, `route`, `followup`) exit `2` outside tmux.
- State is one JSON file (`~/.local/state/agent-team/state.json`,
  override `$TEAMCTL_STATE`). All access is serialized with an `flock`:
  **concurrent teamctl calls from multiple agents are safe** — they
  cannot race a pane into orphanhood.
- **One role = one teammate = one pane.** A second `spawn`/`dispatch` on
  a live role is refused (exit `1`). Roles are your unit of ownership:
  never point two teammates at the same file.
- **In a git repo, a teammate gets its own worktree by default** (branch
  `teamctl/<role>`, directory under the state dir). Its writes cannot
  touch the main tree until `teamctl land <role>`. Opt out per launch
  with `--no-worktree`. Outside a git repo: plain cwd, one stderr note.
- **teamctl refuses instead of guessing.** Exact session id or `followup`
  refuses; several providers and no preference → it asks; an existing
  `teamctl/<role>` branch → refused with the ways out; un-landed work at
  shutdown → kept and reported, never discarded; unknown states are
  reported as unknown (`unknown`, `?%`, `auth not probed`).
- Model ids pass through to the provider CLI **verbatim**; teamctl has no
  model list. `--model`/`--effort` beat config defaults. A provider with
  no effort control (gemini; customs with `effort_args = []`) drops
  `--effort` with one stderr note — never silently.
- teamctl never reads or stores credentials. It only checks for the
  *presence* of each CLI's auth artifacts; sign-in always happens in the
  vendor CLI itself.
- Config: `~/.config/agent-team/config.toml`, read/written via
  `teamctl config` (dotted keys — see §7). Never hand-edit while a
  `config` call may be running.

## 2. Exit-code contract

| Code | Meaning | Applies to |
|---|---|---|
| `0` | success (for `result`: also "still running" without `--wait`, and "update available" for `update --check` — parse stdout) | all |
| `1` | operational failure: unknown role, role conflict, task failed, teammate died, send failed, no available provider, land conflict/cancel, refused action | all |
| `2` | precondition/usage error: not inside tmux, unknown provider, `--worktree` outside a git repo, bad arguments | pane-creating commands, `land`, argparse |
| `3` | internal refusal rendered from a caught error (message on stderr) | any |

stderr carries the reason; stdout carries the product. Parse stdout only.

## 3. Vocabulary

### 3.1 Provider states (the lattice)

Reported by `teamctl providers [--json]` (and colored in `init`):

| State | Semantics |
|---|---|
| `ready` | CLI on PATH, signed in, usage numbers known (shown inline) |
| `quiet` | CLI on PATH, signed in, **no usage data yet** — fully usable; each surface shows the exact wake hint. Gemini is permanently quiet (no local usage feed exists). A custom provider with no auth config shows `quiet — auth not probed` and stays routable |
| `locked out` | CLI on PATH but not signed in |
| `not installed` | CLI not on PATH (residual usage artifacts are flagged, never rendered live) |
| `unknown` | auth artifacts exist but can't be read — reported, never guessed |

`route` excludes not-installed / locked-out / auth-unknown / cached
exhausted or auth-error providers, then ranks the survivors by
**headroom** (default): most remaining quota wins, no-data ranks as 0%
used, preference order breaks ties. `routing.strategy = "preference"`
restores strict order. Exhaustion signals auto-expire at reset time.

### 3.2 Teammate states

`teamctl list [--json]` (lifecycle; derived fresh, never stored) and
`teamctl status [role] [--json]` (activity classification):

| State | Source | Meaning | Your move |
|---|---|---|---|
| `active` | list | interactive teammate, pane alive | `send` / `status` / `shutdown` |
| `input?` | list | fast flag: an approval dialog matched | `teamctl status` for detail, then `send` the answer |
| `busy` | status | pane content changing between samples | leave it alone |
| `needs-input` | status | stable pane matching an approval-dialog shape (detail = the matched line) | `send <role> "y"` / the requested answer |
| `idle` | status | stable pane, no dialog (unrecognized TUIs degrade here) | next task or `shutdown` |
| `running` | both | dispatched task in flight | `result <role> --wait` |
| `done` | both | dispatched task finished, `rc == 0` | `result`; `followup`; `land` if it wrote; `shutdown` |
| `failed(N)` | both | dispatched task exited N | `result` prints the stderr tail — triage |
| `died` | both | pane/process gone before writing status | recovery recipe R6 |
| `gone`/lost | status/state | interactive pane vanished without shutdown | `teamctl resurrect` (see R15) |

### 3.3 Handoff directory (dispatch protocol)

Per-role at `~/.local/state/agent-team/<role>/`:

| File | Contents |
|---|---|
| `task.md` | the dispatched task text (context-file already appended) |
| `result.json` | teammate stdout (the JSON you asked the task for — or raw text) |
| `error.log` | teammate stderr, written durably as it happens |
| `status` | absent while running; `DONE <rc>` or `DONE <rc> <SIGCAUSE>` (e.g. `DONE 137 SIGKILL`) when finished |
| `pid` | wrapper PID |
| `session` | captured exact-session id (refreshed whenever artifacts yield one) |

Prefer `teamctl result` over reading these directly — it also refreshes
exact-session ids and records provider exhaustion signals.

### 3.4 Worktree records

A teammate's state entry carries `worktree: {path, branch, repo,
base_sha}`; `~/.local/state/agent-team/worktrees.json` is the durable
registry that **outlives the state entry** (so `land`/`worktree
list|prune` work after shutdown and reboot). teamctl only ever runs
git's non-forced commands — `worktree remove`, `branch -d` — so git's
own refusals backstop every cleanup decision.

## 4. Command reference

### spawn — interactive teammate

    teamctl spawn [--provider PROVIDER] [--prompt PROMPT] [--model MODEL]
                  [--effort EFFORT] [--cwd CWD] [--worktree | --no-worktree]
                  [--dry-run] role

stdout on success: `spawned teammate '<role>' (<provider>[/<model>]) in pane %N`.
`--dry-run` prints the exact provider launch line and touches nothing
(no worktree is allocated). No `--provider`: the configured routing
preference decides; several providers and no preference ⇒ teamctl
**asks** rather than guessing (in headless use, always pass
`--provider` or configure `routing.preference`).

### dispatch — headless task, watchable pane

    teamctl dispatch [--provider PROVIDER] --task TASK [--context-file CONTEXT_FILE]
                     [--model MODEL] [--effort EFFORT] [--cwd CWD]
                     [--worktree | --no-worktree] role

stdout: `dispatched '<role>' (<provider>…)`. The pane shows the run live;
with the default `[layout] keep_finished` it stays open (visibly done)
until `shutdown`. `--context-file F` appends F's contents to the task.

### result — collect a dispatch

    teamctl result [--wait] [--timeout TIMEOUT] role

Without `--wait`: prints `<role>: running` (exit 0) or the result.
With `--wait`: blocks (default `--timeout 600` seconds), **fails fast
(exit 1) if the teammate dies before writing status** — you will not hang
on a corpse. Success prints `<role>: done` then the result; if the result
parses as JSON it is pretty-printed. Ask for JSON in your task text and
parse everything after the first line.

### followup — another turn, exact same provider session

    teamctl followup --task TASK role

Resumes the *captured session id* (see §6 table). Exits 1 and refuses if
no id was captured — it never guesses "most recent". Gemini sessions are
project-scoped; the follow-up automatically reuses the dispatch cwd.
Collect with `result` again.

### route — pick the provider with the most headroom, then dispatch

    teamctl route --task TASK [--providers PROVIDERS] [--model MODEL]
                  [--effort EFFORT] [--cwd CWD] [--worktree | --no-worktree]
                  [--dry-run] role

stdout line 1 names the pick and every number it used:
`route: selected codex (headroom: codex 12% used < claude 63% < grok ?% ·
preference tiebreak claude>codex>grok; skipped gemini: not installed)` —
unknowns print as `?%`, stale probe data is flagged with a refresh hint.
`--dry-run` adds `dry-run: <exact provider argv>` and dispatches nothing.
Exit 1 with per-provider reasons on stderr when nothing is available.

### status — busy / needs-input / idle

    teamctl status [role] [--json] [--watch] [--interval INTERVAL]

Classifies interactive mates with two pane samples ~0.7s apart (busy =
content changed; needs-input = stable + provider waiting-pattern hit,
detail shows the matched line; idle = everything else, including
unrecognized TUIs — never a wrong strong claim). Dispatch mates report
their lifecycle state. `--watch` polls in the foreground and prints
transitions until Ctrl-C. Transitions observed by `status`/`list`/
`--watch` fire the `[notify] command` hook with env `TEAMCTL_ROLE`,
`TEAMCTL_MATE_STATE`, `TEAMCTL_PREV_STATE` (deliberately not
`TEAMCTL_STATE` — that is the state-file override). No daemon: unwatched
transitions don't fire.

### land — merge a teammate's worktree branch back

    teamctl land [--into INTO] [--checkpoint-only] [--keep] [--yes]
                 [--dry-run] [--json] role

Flow: review (`--dry-run` prints diffstat + commit/dirty counts;
`--json` for machines) → checkpoint uncommitted work with consent
(`--yes` skips the prompt; declining cancels the land) → `merge --no-ff`
into the repo's **checked-out** branch (`--into` only asserts it —
teamctl never switches branches; a dirty root is refused) → cleanup
(worktree + branch removed once provably landed; `--keep` skips).
Conflicts abort the merge and report — tree left clean, exit 1. Works on
live roles, shut-down roles, and after reboots (registry lookup).
Refuses while the teammate is still active.

### worktree — audit / recovery

    teamctl worktree {list,prune} [--json] [--dry-run]

`list`: every teamctl-created worktree — role, branch, live/orphan,
un-landed state. `prune`: removes only worktrees that provably hold
nothing (never a live teammate's, never unique work); `--dry-run`
previews.

### resurrect — rebuild the roster after a crash/reboot

    teamctl resurrect [--dry-run] [--json] [--yes] [roles ...]

Interactive mates lost without an explicit shutdown are recorded in
state (`lost`, newest 20). `resurrect` respawns them fresh with the
recorded provider/model/effort/cwd/prompt — the opening prompt states
that prior conversation context was NOT restored (teamctl never captured
interactive session ids and never guesses). A surviving worktree is
reused; a fully-gone one is re-allocated; a gone path whose branch
survives is refused (it may hold un-landed work). Dispatch mates never
need resurrecting — their artifacts persist; use `followup`.

### send — type into a live teammate

    teamctl send [--no-enter] role message

Sends literal keys + Enter to the pane. **No acknowledgment protocol** —
for machine round-trips use `dispatch`/`result`. This is also how you
answer a `needs-input` approval (`send <role> "y"`), and how you ask a
provider's own TUI for its account numbers (`send <role> "/usage"`).

### list / providers / usage — status (machine-readable)

    teamctl list [--json]
    teamctl providers [--json]
    teamctl usage [--json] [--probe [provider|all]]

`usage --probe` opens the provider's own TUI in a hidden background tmux
session to scrape fresh numbers — explicit only, never automatic; it
starts a real provider session. Claude is not probed (statusline cache
is cheaper); gemini has no probe (nothing parseable exists).

Full `--json` surface list: `list`, `status`, `providers`, `usage`,
`worktree list`, `land --dry-run`, `resurrect --dry-run`.

### shutdown — verified teardown, strand-proof

    teamctl shutdown role

Kills the whole process tree, verifies it died, closes the pane, clears
state and handoff artifacts. Worktree reconciliation runs after death is
verified: a provably-clean worktree is removed; ANY un-landed work (dirty
files or unmerged commits) keeps the worktree + branch and prints the
`teamctl land` way out. Shutting down a crash-lost role clears its lost
record. Allow ~4s.

### models / config / settings / init / lead / doctor / update / uninstall

    teamctl models [provider]        # best-effort discovery; ids pass through verbatim
    teamctl config [key] [value] [--menu]
    teamctl settings                 # cockpit; no-TTY prints values + config one-liners
    teamctl init [--custom] [--yes]  # --yes: scripted, no chrome, config only
    teamctl lead {on,off,status} [--cli {claude,codex,grok,gemini,all}] [--hook]
    teamctl doctor                   # exit 0 ok / 1 warn / 2 fail; includes environment
                                     #   (WSL note), worktree orphans, lost teammates
    teamctl update [--check]         # from the recorded install source
    teamctl uninstall [--yes]        # run `teamctl lead off` first
    teamctl                          # bare, on a terminal: launch the default lead session

## 5. Recovery recipes (deterministic: condition → action)

- **R1 · exit 2, `not inside a tmux session`** → you are not in tmux.
  Attach or create one (`tmux new-session -A -s teamctl`), re-run.
- **R2 · exit 2, unknown provider** → `teamctl providers`; use an
  installed provider name (`claude|codex|grok|gemini` or a configured
  custom name), or install/sign in.
- **R3 · exit 1, `teammate '<role>' already exists`** → the role is
  live. Either continue it (`send` for interactive, `followup` for
  dispatch) or `teamctl shutdown <role>` then retry. Never rename-and-
  respawn to dodge the conflict — that leaks a pane you no longer track.
- **R4 · exit 1 on `spawn`/`dispatch`, finished teammate holds the role**
  → `teamctl shutdown <role>` (clears state + artifacts), retry.
- **R5 · `result` exit 1, `no teammate '<role>'`** → `teamctl list
  --json`; you misspelled the role or already shut it down.
- **R6 · `result` exit 1, `died before writing status` / state `died`** →
  read the stderr tail `result` printed. If empty: the provider died
  pre-output — run `<provider> --version` in a shell; on macOS
  `codesign -v "$(which <provider>)"`; if the CLI is broken, re-dispatch
  the same task via `teamctl route` (it will pick another provider).
- **R7 · `result` shows `failed(N)` with a limit/auth message** → teamctl
  already recorded the exhaustion signal; `teamctl route` now skips that
  provider until its reset time. Re-dispatch via `route`; tell the user.
- **R8 · `result --wait` timed out (long task still `running`)** →
  confirm liveness with `teamctl list`; if `running`, re-issue with a
  bigger `--timeout` (e.g. 1800). If `died`, go to R6.
- **R9 · `route` exit 1, no available provider** → stderr lists
  per-provider reasons. `teamctl usage` for reset times; either wait,
  ask the user to sign a CLI in, or reduce scope.
- **R10 · `send` exit 1, failed to send** → the pane is gone;
  `teamctl list` reconciles state. Respawn if still needed.
- **R11 · `followup` exit 1, no captured session id** → the original
  dispatch produced no parseable id (provider format drift). Start a
  fresh `dispatch` and include the prior result as `--context-file`.
- **R12 · usage numbers look stale** → `teamctl usage` labels data age;
  refresh with `teamctl usage --probe all` (explicit; opens hidden
  provider TUIs) before a large dispatch wave.
- **R13 · spawn/dispatch exit 2, `branch teamctl/<role> already exists`**
  → un-landed work from a previous holder of the role. Land it
  (`teamctl land <role>` — works post-shutdown), have the user delete it
  (`git branch -D` — teamctl never forces), or pick another role name.
- **R14 · `land` exit 1, merge conflicts** → the merge was aborted; the
  user's tree is clean; the worktree is untouched. Report the conflict;
  resolving is a human (or explicitly-tasked-teammate) decision:
  `git -C <repo> merge teamctl/<role>` by hand.
- **R15 · teammates disappeared after a reboot/crash** → `teamctl
  resurrect --dry-run` shows the lost roster and the plan; `resurrect
  --yes` rebuilds interactive mates (fresh sessions — context is honestly
  not restored). Dispatch mates: just `result`/`followup` — their
  sessions resume exactly from disk.
- **R16 · a teammate has been silent too long** → `teamctl status
  <role>`: `busy` = leave it; `needs-input` = the detail column shows the
  blocking prompt, answer with `send`; `idle` = it finished or stalled —
  give it the next instruction or shut it down.
- **R17 · gemini followup fails `Invalid session identifier`** → known
  upstream flake (#24808), visible in error.log. Re-run the same
  `followup` (the id is still captured); if it persists, re-dispatch.

## 6. Session-id capture (what `followup` runs on)

| provider | source |
|---|---|
| claude | `session_id` in the JSON result |
| gemini | `session_id` in the JSON output — present on errors too (error JSON arrives on stderr; both artifacts are checked) |
| codex | `session id: <uuid>` stderr banner; rollout-log filename fallback |
| grok | `sessionId` in the JSON result |
| custom | `session_id_key` (recursive JSON key) or `session_id_regex` (stderr first, then stdout text) |

No id captured → `followup` refuses. That is correct behavior; see R11.

## 7. Config keys (dotted, via `teamctl config`)

| Key | Values | Meaning |
|---|---|---|
| `routing.preference` | comma list, e.g. `codex,claude` | headroom tiebreak (default strategy) / the whole ranking (`strategy = preference`); bare spawn/dispatch use the first entry |
| `routing.strategy` | `headroom` \| `preference` | how survivors are ranked (default `headroom`) |
| `providers.<p>.model` | id or empty | default `--model` (empty = CLI's own default) |
| `providers.<p>.effort` | e.g. `high` | default `--effort` (never written for effort-less CLIs) |
| `providers.custom.<name>.*` | see §8 | bring-your-own-CLI block |
| `worktree.enabled` | bool (default `true`) | teammate worktree isolation in git repos |
| `worktree.cleanup` | `auto` \| `keep` | shutdown behavior for provably-clean worktrees |
| `worktree.dir` / `worktree.branch_prefix` | path / string | placement + branch naming (defaults: state dir, `teamctl/`) |
| `notify.command` | command string | run on observed status transitions (argv via shlex, env context) |
| `lead.delegation` | `ask` \| `always` \| `manual` | how eagerly a lead delegates (see §9) |
| `lead.chat_provider` / `chat_model` / `chat_effort` | provider / id / level | what bare `teamctl` opens |
| `output.verbosity` | `terse` \| `normal` \| `detailed` | output volume |
| `layout.lead_width` | 20–80 | lead pane % of window width |
| `layout.keep_finished` | bool (default `true`) | finished dispatch panes stay visible until shutdown |
| `usage.probe_stale_minutes` | int | staleness threshold for probe data |
| `update.check` / `update.mode` | bool / `prompt`\|`auto`\|`off` | daily background version check |

Sets are safe: previous file backed up (`config.toml.bak-teamctl`), other
keys preserved, unparseable configs refused rather than replaced.

## 8. Custom providers (`[providers.custom.*]`)

Teach teamctl any CLI that speaks `<cmd> [flags] "<prompt>"` — pure
config, no code. Schema (all `*_args` are argv templates; `{task}`,
`{model}`, `{effort}`, `{session_id}` substitute inside tokens, no shell):

```toml
[providers.custom.<name>]           # name must not shadow a built-in
command       = "mycli"             # required; must be on PATH
headless_args = ["-p", "{task}"]    # {task} required; absent = spawn-only
resume_args   = []                  # [] = follow-ups refused
session_id_key   = ""               # id key in JSON output…
session_id_regex = ""               # …or regex (stderr, then stdout text)
model_args    = ["--model", "{model}"]
effort_args   = []                  # [] = no effort control
interactive_args = []
auth_env      = "MYCLI_TOKEN"       # positive-only signal for customs
auth_files    = []                  # enables real signed-in/out detection
login_hint    = ""
probe_command = ""                  # its TUI usage command
waiting_patterns = []               # approval-dialog regexes for `status`
routable      = true
```

Degrades are honest: malformed blocks are skipped with one stderr warning
(built-ins never affected); no auth config → `quiet — auth not probed`,
still routable; `--effort` on an effort-less provider → dropped with a
note.

A worked real-world example — Google Antigravity's `agy` 1.1.1, verified
live 2026-07-12:

```toml
[providers.custom.agy]
command       = "agy"
headless_args = ["-p", "{task}", "--output-format", "json",
                 "--dangerously-skip-permissions", "--print-timeout", "300s"]
resume_args   = ["--conversation", "{session_id}", "-p", "{task}",
                 "--output-format", "json",
                 "--dangerously-skip-permissions", "--print-timeout", "300s"]
session_id_key   = "conversation_id"   # from its (hidden) JSON output mode
# fallback if that undocumented flag drifts: point --log-file at a per-run
# path via headless_args and use
#   session_id_regex = "conversation=([0-9a-f-]{36})"
model_args    = ["--model", "{model}"] # labels from `agy models`
auth_env      = "ANTIGRAVITY_TOKEN"    # keyring login also works (unprobed)
```

agy caveats, verified live: (1) **macOS over SSH** — agy switches to
file-based token storage in SSH sessions and ignores the keychain, so
headless runs fail auth until one interactive OAuth is done in that
context; start the tmux server from a local/GUI terminal. (2) agy
**self-updates** (~15-min checker) — its flag surface can drift; unknown
`--output-format` values silently fall back to plain text, which the
regex fallback covers.

## 9. The lead identity (operating rules, shipped verbatim)

`teamctl lead on` installs the identity below as a Claude Code skill
(`~/.claude/skills/teamctl-lead/SKILL.md`) plus a compact instructions
block for every detected CLI (`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`,
`~/.grok/AGENTS.md`, `~/.gemini/GEMINI.md`) and an optional per-prompt
hook. If you are a lead agent without lead mode installed, follow it
anyway. Source of truth: `LEAD_SKILL_MD` in the teamctl source — the
standing rules verbatim:

1. **Stay responsive.** Keep the main chat free for the user's dynamic
   tasks; delegate all non-trivial work to teammates.
2. **Decide capacity from live data, not habit.** `teamctl usage` +
   `teamctl providers` before spawning/dispatching anything large;
   `teamctl route` automates the pick; probe before a big wave.
3. **Name teammates by role** — one clear deliverable each.
4. **One owner per file** — reviewers review, they don't co-write.
5. **Zero idle teammates** — `shutdown` the moment a job is done.
6. **Keep the toolchain current** — surface available updates promptly;
   apply only with the user's go-ahead.
7. **The user overrides everything.**

Delegation posture (`teamctl config lead.delegation`): `ask` (default —
ask once per session, offer to remember), `always`, `manual`; whatever
the posture, one — and only one — "this is big, want a team?" suggestion
per session, and a no is final. The per-prompt hook echoes the live value
as `delegation=<value>` on every prompt.

v0.5.0 additions a lead should fold into the same discipline: check
`teamctl status` before assuming a silent teammate is working (answer
`needs-input` blocks via `send`); `teamctl land <role>` when a writing
teammate finishes (review `--dry-run` first); `teamctl resurrect
--dry-run` after any crash/reboot before assuming the roster is gone.

## 10. Agent-driven install

Follow [INSTALL_PROMPT.md](INSTALL_PROMPT.md) exactly. Summary:

1. Read README.md, this guide, and llms.txt first.
2. `curl -fsSL https://raw.githubusercontent.com/ryderderder/teamctl/main/install.sh | bash -s -- --no-init`
   — ask the user before anything with sudo; never auto-install provider
   CLIs (show the official one-liners the installer prints and ask);
   ensure `~/.local/bin` is on PATH.
3. `teamctl init` (express: zero questions) — show the user the summary
   frame; never pick a routing order for them.
4. Verify with `teamctl doctor` and show the output.
5. Report the user's controls: `teamctl settings`, `teamctl lead
   on|off|status`, `teamctl uninstall` (after `teamctl lead off`).

## 11. Safety posture (for agents, briefly)

teamctl never sets a provider's autonomous-mode flags — each teammate
launches with whatever permission posture the *user* configured for that
CLI. `send` types raw keys into live terminals: any process able to run
teamctl can steer every teammate, including a prompt-injected teammate
steering its siblings. Worktree isolation contains a rogue writer's
*writes* to its own branch until a human-reviewed `land` — but it is a
collision guard, not a security boundary. Operate in trusted repos,
prefer container/VM isolation, and honor the user's delegation posture
(§9) before spending their subscriptions.
