# teamctl — the agent's guide

You are (probably) an AI agent about to install, operate, or act as the
**lead** of a teamctl agent team. This file is the operational contract:
every command that matters, every machine-readable surface, and every
refusal you should expect. The human-facing tour lives in
[README.md](../README.md).

teamctl turns a tmux window into an agent team: a lead (you) in the left
pane, teammates — Claude Code / Codex / Grok / Gemini CLI sessions, or any
CLI taught via `[providers.custom.*]` — as panes tiled to the right.
Single-file Python, stdlib only, tmux is the only runtime dependency.

## Culture (why commands refuse)

teamctl **refuses instead of guessing**. Expect — and respect — these:

- `followup` resumes the EXACT captured session id or refuses ("teamctl
  never guesses 'most recent'"). Re-dispatch instead.
- No `--provider` with several available and no configured preference →
  it asks; it never silently picks.
- A worktree branch that already exists → refused with three ways out
  (land it / delete it yourself / rename the role). Never auto-suffixed.
- `land` never switches the user's branches, never auto-stashes, never
  resolves conflicts (a conflicted merge is aborted, tree left clean).
- Unknown states are reported as unknown (`unknown`, `?%`, "auth not
  probed") — never converted to a confident guess.

## Command reference

```
teamctl                              # bare: open the default lead session
teamctl init [--custom] [--yes]      # setup wizard (express is zero-question)
teamctl doctor                       # health check; exit 0 ok / 1 warn / 2 fail
teamctl settings | config [k [v]]    # preferences (cockpit / dotted keys)

teamctl spawn <role> [--provider P] [--model M] [--effort E] [--prompt T]
                     [--cwd D] [--worktree|--no-worktree] [--dry-run]
teamctl dispatch <role> --provider P --task "…" [--context-file F]
                     [--model M] [--effort E] [--cwd D] [--worktree|--no-worktree]
teamctl result <role> [--wait] [--timeout N]
teamctl followup <role> --task "…"   # SAME session, exact id, or refusal
teamctl route <role> --task "…" [--providers a,b] [--dry-run]
teamctl send <role> "…" [--no-enter] # raw keys into a live pane

teamctl list [--json]
teamctl status [role] [--json] [--watch [--interval N]]
teamctl land <role> [--checkpoint-only] [--into BRANCH] [--keep] [--yes]
                    [--dry-run] [--json]
teamctl worktree list|prune [--json] [--dry-run]
teamctl resurrect [role …] [--dry-run [--json]] [--yes]
teamctl shutdown <role>              # always, the moment a role is done

teamctl providers [--json] · usage [--json] [--probe [P|all]] · models [P]
teamctl update [--check] · uninstall [--yes] · lead on|off|status
```

## Machine-readable surfaces (prefer these to scraping tables)

| command | payload |
|---|---|
| `list --json` | role → full state entry + derived lifecycle `state` |
| `status --json` | role → `{provider, mode, state, detail}`; interactive states are `busy` / `needs-input` / `idle` (detail = the matched prompt line) |
| `providers --json` | provider → `{state, detail}` (the 5-word lattice) |
| `usage --json` | one key per routable provider (windows or `null`) + `probes` + `states` |
| `route … --dry-run` | selection + reason line with every % it used (`?%` = unknown) |
| `land <role> --dry-run --json` | `{role, branch, path, repo, base_sha, target, uncommitted_changes, unlanded_commits}` |
| `worktree list --json` | per-worktree `{role, branch, path, repo, exists, unique_work, detail, owner_alive}` |
| `resurrect --dry-run --json` | role → `{action, cwd, worktree, note, provider, model, effort, lost_at}` |

## The lead playbook

1. **Capacity from live data, never habit**: `teamctl usage` +
   `teamctl providers` before spawning anything large. `route` automates
   the pick — default strategy is **headroom** (most remaining quota wins
   among usable providers; preference order breaks ties; exclusions
   happen first, so an exhausted provider is never picked however idle).
2. **One role, one deliverable, one owner per file.** Worktree isolation
   (on by default in a git repo) makes the one-owner rule mechanical —
   but you still assign distinct work.
3. **Watch for blocked teammates**: `teamctl status` — `needs-input`
   means an approval dialog is holding a teammate hostage; the detail
   column shows the prompt line. `[notify] command` in config runs your
   hook on observed transitions (env: `TEAMCTL_ROLE`,
   `TEAMCTL_MATE_STATE`, `TEAMCTL_PREV_STATE` — deliberately NOT
   `TEAMCTL_STATE`, which is the state-file path override).
4. **Close the loop**: when a writing teammate finishes, `teamctl land
   <role>` — review the `--dry-run` plan, land, and the worktree cleans
   itself up. `shutdown` the role the moment it is done. Shutdown never
   discards work: anything un-landed is kept and reported.
5. **After a crash/reboot**: `teamctl resurrect --dry-run` shows what was
   lost; `resurrect` rebuilds interactive teammates (fresh sessions —
   prior context is honestly NOT restored) and points dispatch mates at
   `followup`, which still resumes their exact sessions from disk.

## Worktree lifecycle (writing teammates)

```
spawn/dispatch in a git repo            # branch teamctl/<role>, own dir
  └─ teammate works in isolation        # physically cannot collide
teamctl land <role> [--dry-run first]   # checkpoint (with consent) → merge
  └─ merge --no-ff into the CHECKED-OUT branch; conflicts abort cleanly
teamctl shutdown <role>                 # clean worktree removed;
                                        # un-landed work KEPT + reported
teamctl worktree list|prune             # audit/recovery, incl. orphans
```

teamctl never passes `-D`, `--force`, `-f`, `--hard`, `reset`, or `clean`
to git — enforced by an audit test. Disk note: each worktree is a full
checkout of tracked files; untracked artifacts (node_modules, venvs,
build dirs) are per-worktree by design.

## Custom providers (`[providers.custom.*]`)

Teach teamctl any CLI that speaks `<cmd> [flags] "<prompt>"` — pure
config, no code. Full schema in the README. A worked example, verified
live against Google Antigravity's `agy` 1.1.1 (2026-07-12):

```toml
[providers.custom.agy]
command       = "agy"
headless_args = ["-p", "{task}", "--output-format", "json",
                 "--dangerously-skip-permissions", "--print-timeout", "300s"]
resume_args   = ["--conversation", "{session_id}", "-p", "{task}",
                 "--output-format", "json",
                 "--dangerously-skip-permissions", "--print-timeout", "300s"]
session_id_key   = "conversation_id"   # from its (hidden) JSON output
# fallback if that flag drifts: session_id_regex over its --log-file line
#   "Print mode: conversation=([0-9a-f-]{36}), sending message"
model_args    = ["--model", "{model}"] # labels from `agy models`
auth_env      = "ANTIGRAVITY_TOKEN"    # positive-only; keyring login also works
```

Caveats to pass on to your human, verified live:
- **macOS + SSH**: agy switches to file-based token storage in SSH
  sessions and ignores the keychain — headless runs then fail auth until
  one interactive OAuth is completed in that context. Start the tmux
  server from a local/GUI terminal, not purely over SSH.
- agy **self-updates** (~15 min checker): its flag surface can drift;
  unknown `--output-format` values silently fall back to plain text, and
  the regex fallback above covers that.
- A custom provider with no `auth_files` shows as `quiet — auth not
  probed` and stays routable: the user configured it on purpose.

## Session ids (what `followup` runs on)

| provider | source |
|---|---|
| claude | `session_id` in the JSON result |
| gemini | `session_id` in the JSON output — present on errors too (error JSON arrives on stderr; both artifacts are checked). Sessions are project-scoped: follow-ups reuse the dispatch cwd automatically. Upstream #24808: resume can intermittently fail — visible in error.log, re-triable. |
| codex | `session id: <uuid>` stderr banner; rollout-log filename fallback |
| grok | `sessionId` in the JSON result |
| custom | `session_id_key` (recursive JSON key) or `session_id_regex` (stderr, then stdout text) |

No id captured → `followup` refuses. That is correct behavior; re-dispatch.
