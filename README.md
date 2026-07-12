# teamctl

**Your AI subscriptions, working as one team.**

You're already paying for Claude Code — and maybe Codex, Grok, Gemini,
or Antigravity. teamctl turns a tmux window into one team: a lead agent
in the left pane, teammates as labeled panes to the right, and every
task routed to whichever subscription has the most quota left right now.

**How it works.** Every teammate is a real provider CLI in a real tmux
pane, running under your own logins — watchable, steerable, disposable.
A lead (you, or a lead agent) spawns interactive teammates or dispatches
headless tasks whose results come back as JSON; follow-ups resume the
*exact same* provider session; writers each get their own git worktree
so parallel edits physically can't collide, and `teamctl land` merges a
teammate's branch back once you've reviewed it. Single-file Python,
stdlib only; tmux is the only dependency.

<!-- Hero demo — rendered per docs/recordings/demo-storyboard.md;
     re-render via docs/recordings/demo-v2.tape. -->
![One task fanned across providers: the lead checks usage, dispatches teammates as labeled tmux panes, watches them work in parallel, reads JSON results back, and shuts the team down cleanly](docs/assets/demo.gif)

[![ci](https://github.com/ryderderder/teamctl/actions/workflows/ci.yml/badge.svg)](https://github.com/ryderderder/teamctl/actions/workflows/ci.yml)
[![release](https://img.shields.io/github/v/release/ryderderder/teamctl)](https://github.com/ryderderder/teamctl/releases)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## Install

**Give your agent teamctl.** Paste this one line into Claude Code,
Codex, Grok, Gemini, or Antigravity — it installs teamctl from GitHub
and verifies its own work:

```text
Fetch and follow instructions from https://raw.githubusercontent.com/ryderderder/teamctl/main/INSTALL.md
```

Or install it yourself:

```sh
curl -fsSL https://raw.githubusercontent.com/ryderderder/teamctl/main/install.sh | bash
```

The one-liner drops you into tmux with providers detected and sane
defaults written, in seconds. `--no-init` skips the tmux takeover,
`teamctl doctor` health-checks the result, and `teamctl uninstall`
reverses everything (backups first).

## What you can tell it

With lead mode on (`teamctl lead on`), you just talk to your lead agent:

> "Fan this question out to three researchers on different providers and
> compare their answers."

> "Build the /orders endpoint. Have a different provider review the
> diff, and land the branch when the review comes back clean."

> "Route this audit to whichever subscription has the most headroom, and
> follow up on the same session with the FIXMEs afterwards."

> "Who's stuck?" · "Land the builder's work and shut everyone down."

Everything the lead does maps to plain commands you can also type
yourself:

```sh
teamctl spawn <role> --prompt "…"   # interactive teammate in a labeled pane
teamctl dispatch <role> --task "…"  # headless task → JSON result
teamctl result <role> --wait        # collect it (fails fast if the teammate dies)
teamctl followup <role> --task "…"  # another turn, exact same session
teamctl route <role> --task "…"     # auto-pick: most quota headroom wins
teamctl status                      # busy / blocked on an approval / idle
teamctl land <role>                 # merge a writer's worktree branch back
teamctl shutdown <role>             # verified teardown — nothing stranded
```

(Also: `list`, `send`, `worktree list|prune`, `resurrect` — the roster
survives reboots — `usage`, `providers`, `models`, `settings`, `doctor`,
`update`.)

## Learn more

- **[docs/GUIDE.md](docs/GUIDE.md)** — the complete guide: every feature
  in depth, the full configuration reference, security posture, FAQ, and
  the honest limitations.
- **[docs/AGENT_GUIDE.md](docs/AGENT_GUIDE.md)** — the machine contract:
  exact syntax, exit codes, state vocabulary, every `--json` surface,
  recovery recipes, and the custom-provider schema (bring any CLI —
  Antigravity's `agy` is the worked example).
- **[docs/use-cases.md](docs/use-cases.md)** — real workflows, written
  to be typed: parallel research, builder/reviewer, usage-aware batch
  ops, worktree landing, the self-driving lead.
- **[llms.txt](llms.txt)** — the agent orientation index.
- `teamctl usage` / `teamctl providers` — live meters and sign-in states,
  honestly labeled (data only where providers expose it; "unknown" is
  said out loud, never invented).

## Requirements & security, briefly

macOS/Linux (WSL runs as Linux) · tmux · Python 3.11+ · at least one
signed-in provider CLI: `claude`, `codex`, `grok`, `gemini` — or teach
teamctl any CLI via a `[providers.custom.*]` config block. git is needed
only for worktree isolation (on by default *inside git repos*).

Hands-off teams mean running the vendor CLIs in their autonomous modes.
teamctl never sets those flags itself — each teammate launches with
whatever permission posture you configured for that CLI — but if your
defaults are autonomous, every teammate is too. Run agent teams in a
container/VM where possible, against inputs you trust. teamctl never
reads, stores, or transmits credentials: sign-in happens in each
vendor's own CLI, and nothing about your subscription access is wrapped
or proxied. Full details, honest limitations included:
[docs/AGENT_GUIDE.md](docs/AGENT_GUIDE.md).

## Credits & license

Inspired by Claude Code's experimental
[agent teams](https://code.claude.com/docs/en/agent-teams) — the
lead-and-teammates shape, reimagined on plain tmux so any provider's CLI
plays on equal footing. MIT — see [LICENSE](LICENSE).
