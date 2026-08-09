# Hero demo GIF v2 — storyboard

**The shot:** one real task flows through **all three providers at once** —
research to Grok, implementation to Claude, review to Codex — as labeled
tmux panes the viewer can watch working, then three JSON results come back
to the lead, get synthesized, and the team is torn down clean. No fakery:
every teammate is the real provider CLI doing real work on a real file.

Replaces `docs/assets/demo.gif` (the v0.3.0 shell-provider recording) as
the README hero; the old GIF's mechanics-only framing stays useful for
docs/recordings regression checks but is no longer the front door.

---

## 1. The task (real, small, legible)

The recording work dir is seeded with **`tinylog.py`** — a ~35-line,
self-explanatory log-filtering CLI (see `setup-demo-live.sh` in this
directory). The task the lead fans out:

> **Add a `--json` output flag to tinylog.py.**

Why this task: it's real code work a GitHub visitor instantly understands;
it decomposes into three *genuinely parallel* workstreams (no teammate
waits on another, so GIF wall-clock = slowest teammate, not the sum); and
each subtask plays to a distinct role so the casting reads as intentional.

## 2. Casting (decision + alternatives)

| Role | Provider | Model | Why cast this way |
|---|---|---|---|
| `researcher` | **grok** | grok-4.5 | survey/recommendation work; fast; shows the third logo working |
| `builder` | **claude** | sonnet | the actual code edit — the highest-stakes subtask on the best-known coding agent |
| `reviewer` | **codex** | (CLI default, `--effort low`) | independent audit of the existing file's edge cases; Codex's review posture is a natural fit |

All three run as **headless `dispatch`** (not `spawn`): dispatch panes
stream the provider's real work, close themselves when done, and give the
lead a JSON `result` to read back — which is the product story.

**For Ryder to confirm — casting alternatives:**
- **A (storyboarded):** research→grok, build→claude, review→codex.
- **B:** research→codex, build→claude, review→grok — if you'd rather the
  Codex pane show longer/denser output (its reasoning stream is chatty).
- **C:** build→codex, review→claude — strongest if you want to counter
  "this is just a Claude wrapper" skepticism by giving the code edit to a
  non-Anthropic model. Costs the "Claude writes the code" familiarity.
- Any casting works mechanically; only the three `--provider` flags and the
  caption line change in the tape.

## 3. Beat-by-beat

Terminal: **1080×620, FontSize 14, 20fps** (identical to the existing
harness geometry — a 100×30-ish tmux window). Captions are typed shell
comments in the lead pane — legible, honest, and they need no video
editing. Target length **≤75s**; budget below.

| # | t (target) | Lead pane action | What the viewer sees / learns |
|---|---|---|---|
| 0 | 0–4s | caption: `# one task: add --json to tinylog.py` then `# one team: three AI subscriptions` | the premise, in words, before anything moves |
| 1 | 4–9s | `orchestrator usage` | real usage %/reset times per provider — capacity is data here |
| 2 | 9–12s | caption: `# cast: research->grok · build->claude · review->codex` | the routing decision, spelled out |
| 3 | 12–16s | `orchestrator dispatch researcher --provider grok --task "…recommend a JSON schema…"` | first pane opens: `researcher · grok-4.5` border label; lead prints `dispatched 'researcher' (grok…)` |
| 4 | 16–20s | `orchestrator dispatch builder --provider claude --model sonnet --task "…add the flag, print the diff…"` | second pane: `builder · sonnet` |
| 5 | 20–24s | `orchestrator dispatch reviewer --provider codex --effort low --task "…edge cases the flag must not break…"` | third pane: `reviewer · <codex default>` — **the money frame: three vendors' CLIs visibly working at once** |
| 6 | 24–29s | `orchestrator list` | ROLE/PROVIDER/PANE/STATE table, three rows `running` |
| 7 | 29–36s | (hold, no typing) | panes stream; viewer just watches the team work |
| 8 | 36–42s | `orchestrator result researcher --wait` | grok's JSON recommendation, pretty-printed; its pane has closed itself; **--wait self-syncs the recording** |
| 9 | 42–48s | `orchestrator result reviewer --wait` | codex's JSON verdict list |
| 10 | 48–56s | `orchestrator result builder --wait` | claude's unified diff — the actual code change, held longest |
| 11 | 56–59s | caption: `# schema from grok · diff from claude · edge cases from codex — synthesized` | the lead's synthesis moment |
| 12 | 59–68s | `for r in researcher builder reviewer; do orchestrator shutdown $r; done` | panes close one by one; process-tree-verified teardown |
| 13 | 68–73s | `orchestrator list` → `no active teammates`; caption: `# github.com/ryderderder/orchestrator` | clean end state + pointer |

Every beat is legible without audio: captions carry the narrative, pane
border labels carry the who/what, and the lead pane's own command output
carries the how.

**Overrun valve:** if a take lands at 75–95s because a provider was slow,
add `Set PlaybackSpeed 1.25` to the tape rather than cutting beats
(verified available in vhs 0.11.0). Above ~95s raw, retake — slow takes
also mean idle-looking panes.

## 4. The dispatched tasks (exact text)

Short prompts keep turns fast and output small enough to read on screen:

- **researcher (grok):**
  `Recommend a JSON schema for the --json flag of the log CLI tinylog.py in
  this directory (read it first). One object per entry. Return ONLY JSON:
  {"shape": {...}, "rationale": "<=25 words"}.`
- **builder (claude, sonnet):**
  `Add a --json flag to tinylog.py in this directory: one JSON object per
  log entry on stdout; default text output unchanged. Then print ONLY the
  unified diff of your change.`
- **reviewer (codex, --effort low):**
  `Read tinylog.py. List edge cases a new --json output flag must not break
  (empty file, malformed lines, etc). Return ONLY JSON:
  {"edge_cases": ["…", …]} — max 5 items, <=12 words each.`

The builder genuinely edits the seeded file; the diff shown in beat 10 is
the provider's real output. Nothing is staged or pre-written.

## 5. Expected cost (real tokens — the point)

| Teammate | Typical turn | Estimate |
|---|---|---|
| researcher (grok-4.5) | read 35-line file, emit ~200-token JSON | ~2–5k tokens |
| builder (claude sonnet) | small edit + diff | ~5–15k tokens |
| reviewer (codex, low effort) | read + short JSON | ~3–8k tokens |

**Per take: roughly 10–30k tokens total, spread across three
subscriptions** — minutes of one 5h window each; effectively pennies at
API-equivalent rates. Budget 3–5 takes for a keeper (blind pacing means
the first take usually has one timing seam). Check `orchestrator usage` before
a recording session; don't record on a nearly-exhausted window (a
rate-limit error mid-take is a scrapped take *and* a recorded exhaustion
signal in scratch state — harmless, but re-run setup).

## 6. Recording environment & isolation (differs from the shell-provider harness)

The v0.3.0 harness (`docs/recordings/setup-demo.sh`) builds a scratch HOME
with **read-only intent** symlinks to real provider auth. Real dispatches
change the picture — the provider CLIs must *authenticate and write their
own session logs*:

- Scratch HOME at `/tmp/teamhome-live`, scratch tmux socket
  (`-S /tmp/teamhome-live/tmux.sock`), scratch `TEAMCTL_STATE`, scratch
  config, seeded work dir — **Orchestrator never touches your real state, config
  or tmux server.** (Same guarantees as the existing harness.)
- Provider auth/session dirs (`~/.codex`, `~/.claude.json`, `~/.claude`,
  `~/.grok`) are symlinked into the scratch HOME. **Writes go through
  symlinks:** the provider CLIs will append session logs / update their own
  state in your real dirs — exactly as any normal CLI run does. That is the
  cost of a no-fakery recording; flagged here so it's a decision, not a
  surprise.
- **Required preflight (verify, don't assume):** after setup, run one
  smoke turn per provider *inside the scratch env* before rolling:
  `claude -p 'say ok' --output-format json`, `codex exec 'say ok'`,
  `grok -p 'say ok'` (adjust to each CLI's headless syntax as pinned in
  Orchestrator's `headless_argv`). If a CLI balks at the scratch HOME (e.g.
  claude wanting more of `~/.claude` than the symlink set provides), add
  the missing symlink to `setup-demo-live.sh` and re-verify. The
  `ASSUMED` bit is exactly which dot-paths each CLI needs — the smoke test
  converts it to VERIFIED per machine.
- All the v0.3.0 hard-won facts still apply (see
  `docs/recordings/README.md`): **vhs `Wait` is flaky inside tmux → blind
  timed pacing + `result --wait` self-sync; never trust `TMUX_TMPDIR` while
  `$TMUX` is set (the setup script unsets it); login-shell PATH re-pin;
  `shutdown` needs ~4s.** Eyeball every take for type-ahead artifacts.

## 7. Re-record procedure

```sh
cd docs/recordings                       # after these files merge into the repo
./setup-demo-live.sh <pushed-revision>   # scratch env + seeded tinylog.py; pins orchestrator to REV
# preflight: smoke-test all three providers in the scratch env (section 6)
orchestrator usage                            # headroom check (real HOME is fine for this)
vhs demo-v2.tape                         # writes ./demo-v2.gif
# review: length ≤75s, no type-ahead seams, all three panes visibly worked,
# diff readable in beat 10, file size ≤4MB
mv demo-v2.gif ../assets/demo-v2.gif
```

Always re-run setup between takes (teammate state and the seeded file must
be fresh — the builder *edits* tinylog.py). Always pin a revision. Never
run vhs from inside your own tmux without the setup script's `unset TMUX`
env (it handles this).

## 8. Deliverable spec

- `docs/assets/demo-v2.gif` — 1080×620, 20fps, ≤75s, target ≤4MB
  (the v0.3.0 GIF ran 1.4MB at 65s/1080px; real provider output is denser,
  expect ~2–3MB).
- README embed alt-text (already in README-v2.md): describes the full arc
  for screen-reader users and for when GitHub's proxy is slow.
- Keep one **still frame** export of beat 5 (three panes working) — it
  becomes the social-preview/profile still (see gif-placement-plan.md):
  `ffmpeg -i demo-v2.gif -vf "select=eq(n\,<N>)" -vframes 1 demo-hero-still.png`
