# teamctl recipes

Seven real workflows, written to be typed. Each one: the goal, the exact
commands, what you'll see on screen, and what you walk away with.

Conventions used throughout:

- Every teammate appears as a tmux pane labeled `role · model` in its
  border; the lead pane keeps its width on the left.
- `dispatch` = headless task in a watchable pane, result collected as JSON.
  `spawn` = live interactive session you can steer. Both are torn down with
  `shutdown`, which kills the whole process tree and verifies it.
- Output shown is representative (models, percentages and timestamps are
  from a real machine on a real day — yours will differ).
- **Cost:** every recipe spends real tokens on your subscriptions. Sizes
  are noted per recipe; `teamctl usage` before and after shows the damage.

---

## 1. Triangulated research — one question, three independent minds

**Goal:** a load-bearing technical decision (library choice, schema design,
migration strategy) researched by three different models on three different
subscriptions, so agreement means something.

```sh
teamctl usage        # check headroom first — three dispatches land at once
```

```text
PROVIDER  USAGE
claude    5h: 12% used, resets 3:00 PM
codex     5h: 0% used, resets 1:39 AM (now)
codex     weekly: 73% used, resets 12:41 AM (in 142h13m)
grok      quiet — signed in, no usage data yet (probe it: `teamctl usage --probe grok`)
gemini    quiet — gemini exposes no local usage feed — it stays quiet
```

```sh
Q='Should tinylog store entries as JSONL or SQLite? Criteria: append speed,
crash safety, grep-ability, zero deps. Return JSON:
{choice, confidence, reasons: [], risks: []}'

teamctl dispatch scout-claude --provider claude --task "$Q"
teamctl dispatch scout-codex  --provider codex  --task "$Q"
teamctl dispatch scout-grok   --provider grok   --task "$Q"
```

**What you see:** three panes open on the right, each labeled
(`scout-claude · sonnet`, `scout-codex · gpt-5.6-terra`,
`scout-grok · grok-4.5`), each streaming its provider's actual work. The
lead pane prints one line per dispatch:

```text
dispatched 'scout-claude' (claude) …
```

```sh
teamctl list
```

```text
ROLE          PROVIDER  PANE     STATE        CREATED
scout-claude  claude    %12      running      2026-07-12T10:02:11
scout-codex   codex     %13      running      2026-07-12T10:02:14
scout-grok    grok      %14      done         2026-07-12T10:02:17
```

```sh
teamctl result scout-claude --wait
teamctl result scout-codex  --wait
teamctl result scout-grok   --wait
```

Each returns `scout-<x>: done` followed by pretty-printed JSON. Two say
JSONL, one says SQLite? That split is the interesting part — continue the
dissenter's *exact* session:

```sh
teamctl followup scout-codex --task "The other two researchers chose JSONL
for crash-safety-via-append. Steelman their case, then give a final answer."
teamctl result scout-codex --wait
```

```sh
teamctl shutdown scout-claude; teamctl shutdown scout-codex; teamctl shutdown scout-grok
```

**Outcome:** three independent, machine-readable recommendations plus one
adversarial follow-up, in the wall-clock time of the slowest single run.
**Size:** three short headless turns + one follow-up — small; single-digit
minutes of one provider's 5h window each.

---

## 2. Builder + cross-vendor reviewer — nobody grades their own homework

**Goal:** a feature implemented by one provider and reviewed by a
*different* vendor's model — different training, different blind spots.
One owner per file: the builder writes, the reviewer only reads.

```sh
# The builder is interactive: you can watch it and steer it mid-flight.
teamctl spawn builder --provider claude --cwd ~/work/tinylog \
    --prompt "Add a --json flag to tinylog.py: one JSON object per entry on
stdout, default text output unchanged. Add tests. You own this file."
```

```text
spawned teammate 'builder' (claude/sonnet) in pane %15
```

Watch the `builder · sonnet` pane work. Steer it without touching your own
context:

```sh
teamctl send builder "Keep the flag name --json, not --format=json."
```

When the builder reports done, bring in the other vendor:

```sh
teamctl dispatch reviewer --provider codex --cwd ~/work/tinylog \
    --task "Review the uncommitted diff in this repo for correctness, edge
cases (empty file, malformed lines), and API-shape regressions. Return JSON:
{verdict: pass|fail, findings: [{file, line, issue, severity}]}"
teamctl result reviewer --wait
```

**What you see:** the reviewer pane streams its analysis, closes itself when
done; `result` prints the verdict JSON. Findings go back to the *builder* —
the reviewer never edits:

```sh
teamctl send builder "Reviewer findings: <paste>. Address the two 'high'
items, argue with the rest if you disagree."
```

```sh
teamctl shutdown reviewer && teamctl shutdown builder
```

**Outcome:** a change written by one model and independently audited by a
competitor's, with a paper trail of findings. **Size:** one interactive
session (dominant cost) + one short review dispatch.

---

## 3. Competing implementations — let two providers race, judge with a third

**Goal:** for a gnarly problem with a wide solution space, buy two
independent attempts instead of one attempt iterated twice — then have a
third provider judge them cold.

```sh
# Two working copies, one owner each — never two writers in one tree.
git -C ~/work/tinylog worktree add ../tinylog-a && git -C ~/work/tinylog worktree add ../tinylog-b

teamctl dispatch impl-a --provider claude --cwd ~/work/tinylog-a \
    --task "Implement rotation per SPEC.md. When done, print 'git diff' output as your result."
teamctl dispatch impl-b --provider codex  --cwd ~/work/tinylog-b \
    --task "Implement rotation per SPEC.md. When done, print 'git diff' output as your result."

teamctl result impl-a --wait > /tmp/a.diff
teamctl result impl-b --wait > /tmp/b.diff

teamctl dispatch judge --provider grok --cwd /tmp \
    --task "a.diff and b.diff implement the same spec. Score each 1-10 on
correctness, simplicity, test quality. Return JSON: {a, b, winner, rationale}."
teamctl result judge --wait

teamctl shutdown impl-a; teamctl shutdown impl-b; teamctl shutdown judge
```

**What you see:** both implementation panes grinding simultaneously —
the race is the point; wall-clock is max(a, b), not a+b — then a short
judge pane, then a JSON scorecard.

**Outcome:** the better of two independent designs, chosen by a model with
no stake in either. **Size:** the most expensive recipe here — two full
implementation runs; check `teamctl usage` first and give the race to the
two providers with the most headroom.

---

## 4. Usage-aware batch ops — route to whoever has capacity

**Goal:** recurring, longish jobs (audits, doc sweeps, migration batches)
that should burn whichever subscription has headroom *right now*, without
you checking meters.

```sh
# Your standing order, set once:
teamctl config routing.preference "codex,claude,grok"

teamctl route auditor --task "Audit this repo's TODO/FIXME comments; rank
by effort; return JSON." --dry-run
```

```text
route: selected codex (headroom: codex 0% used < claude 44% < grok ?% ·
  preference tiebreak codex>claude>grok; skipped gemini: not installed)
dry-run: codex exec 'Audit this repo'\''s TODO/FIXME comments; ...'
```

`route` excludes providers that are not installed, not signed in, or
known-exhausted, then sends the job to the survivor with the **most
quota left** (v0.5.0's default; your preference order breaks ties —
`teamctl config routing.strategy preference` restores strict order).
Exhaustion signals auto-expire at the provider's reset time, so the
pipeline self-heals as quotas refill. Run it for real,
with a longer leash for a long job:

```sh
teamctl route auditor --task "Audit this repo's TODO/FIXME comments; rank by effort; return JSON."
teamctl result auditor --wait --timeout 1800
```

**What you see:** the route line names the provider *and the reason*; the
pane closes itself when the job finishes; `list` keeps showing the teammate
as `done`; `result` keeps working indefinitely. Next batch, same session:

```sh
teamctl followup auditor --task "Same treatment for XXX and HACK comments."
```

If a provider hits its limit mid-run, `result` records the signal and the
*next* `route` walks past that provider automatically.

```sh
teamctl shutdown auditor    # clears state + handoff artifacts for the role
```

**Outcome:** a pipeline that keeps moving across quota cliffs. **Size:**
whatever your batch is — the win is *where* it lands, not how big it is.

---

## 5. Live steering — an interactive teammate as a second pair of hands

**Goal:** a long debugging or exploration session where you want a second
agent working a parallel thread — visibly, interruptibly — while you stay
in your own flow.

```sh
teamctl spawn tracer --provider grok --cwd ~/work/api \
    --prompt "Reproduce the 500 on POST /orders with the seed data in
fixtures/. Narrate what you try."
```

The `tracer · grok-4.5` pane is a full interactive CLI session. Glance at
it while you work; nudge it when it drifts:

```sh
teamctl send tracer "Stop guessing at the ORM — read migrations/0042 first."
```

Ask the provider's own UI for anything teamctl doesn't wrap — `send` types
real keys into a real terminal:

```sh
teamctl send tracer "/usage"       # the provider's own account numbers
```

When the thread pays off, have it leave a durable artifact before teardown:

```sh
teamctl send tracer "Write your findings to notes/500-repro.md, then say DONE."
teamctl shutdown tracer
```

**Outcome:** a parallel investigation you could watch the whole time,
ending in a file, not a scrollback. **Size:** one interactive session;
whatever you let it run.

---

## 6. The self-driving team — lead mode end to end

**Goal:** stop typing teamctl commands yourself. Your lead agent runs the
whole playbook: capacity check → casting → dispatch → synthesis → teardown.

```sh
teamctl lead on       # manager identity into every detected CLI, reversibly
```

Then, in your lead agent's chat (any provider):

> "Add rate limiting to the API server. Use the team."

**What you see:** the lead runs `teamctl usage` and `teamctl providers`,
picks casting from live capacity, and the panes bloom on their own —
`researcher · grok-4.5`, `builder · sonnet`, `reviewer · gpt-5.6-terra` —
each dispatched, collected, and shut down as it finishes. You interject at
any time, either to the lead or straight into a teammate's pane with
`teamctl send`.

How eagerly the lead does this is yours to set:

```sh
teamctl config lead.delegation ask      # ask | always | manual
```

And everything is reversible:

```sh
teamctl lead status
teamctl lead off      # removes exactly what `on` installed, with backups
```

**Outcome:** the demo GIF at the top of the README, as your daily default.
**Size:** the lead adds one cheap planning layer on top of whatever work
you asked for — and because it checks `usage` first, it spends your
quietest subscription, not your busiest.

---

## 7. Parallel writers, zero collisions — worktrees and the land step

**Goal:** several teammates *writing code* in the same repo at once,
with physically-impossible collisions and an auditable merge for each
stream of work. (New in v0.5.0 — and on by default in a git repo.)

```sh
# Two writers, one repo — each automatically gets its own branch
# (teamctl/<role>) checked out in its own worktree under the state dir.
teamctl spawn api-builder --provider claude --cwd ~/work/server \
    --prompt "Implement the /orders endpoints per docs/api.md. You own orders.py."
teamctl spawn cli-builder --provider codex --cwd ~/work/server \
    --prompt "Add the orders subcommands to the CLI. You own cli.py."

teamctl list        # each row shows its worktree branch: ⌂ teamctl/api-builder
```

They cannot touch your tree or each other's — different directories,
different branches, one shared object store. When a stream is done:

```sh
teamctl land api-builder --dry-run    # the plan: diffstat, counts, target
teamctl land api-builder              # checkpoint (asks) → merge --no-ff
                                      #   into YOUR checked-out branch →
                                      #   worktree + branch cleaned up
teamctl shutdown api-builder
```

**What `land` refuses to do** (each with the reason printed): switch
your branches, merge over a dirty root tree, auto-resolve conflicts (the
merge is aborted, your tree left clean), or land uncommitted work
silently. And `shutdown` can never strand anything: a worktree with
un-landed work is kept and reported — `teamctl land` still works after
the teammate is gone, even after a reboot. `teamctl worktree list`
audits every worktree teamctl ever made; `worktree prune` reclaims only
what provably holds nothing.

**Outcome:** the "one owner per file" rule enforced by git mechanics
instead of prompt discipline — and every teammate's work arriving as one
reviewable merge. **Size:** disk for one checkout of tracked files per
writer (objects shared); untracked artifacts (node_modules, venvs) are
per-worktree by design.

## 0. Cold start — the front door and the health check

```sh
teamctl            # bare: opens your default lead chat in the teamctl
                   # tmux session, lead mode on — the whole experience
                   # in one word. (After a reboot it also offers
                   # `teamctl resurrect` if teammates were lost.)
teamctl doctor     # when anything looks off: environment (incl. WSL),
                   # python/tmux, provider states, config sanity,
                   # statusline wiring, orphaned worktrees, lost
                   # teammates. Exit 0 ok / 1 warn / 2 fail.
```
