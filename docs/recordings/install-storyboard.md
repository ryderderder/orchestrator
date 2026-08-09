# Install GIF v2 — storyboard

**The shot:** a cold machine, one pasted line, and ~25 seconds later the
viewer is *inside* a configured tmux session looking at the twelve-line
dark room — with proof the tool is alive. The install one-liner is the
product's first promise; this GIF is that promise kept, on camera.

---

## 1. Why the old install.gif underwhelmed (autopsy)

From the v0.3.0 tape (`docs/recordings/install.tape`) — these are its
literal contents, not guesses:

- **Two beats total:** type the curl line → one blind `Sleep 10s` → 8s
  static hold. Nothing else ever happens.
- **Zero framing:** no captions, no setup, no payoff line. The viewer gets
  a text bomb of installer output at scroll speed, then a still card, with
  no cue about what any of it means or where to look.
- **The best moment is uncaptioned.** The terminal swapping into tmux and
  the dark-room frame materializing is the aesthetic centerpiece — played
  cold, it reads as a glitch, not a reveal.
- **The promise is never proven.** The whole pitch is "you land in a
  *working* session" — but the recording ends at a static frame. Not one
  command is run in the session we supposedly landed in.
- **One 10s sleep covers five stages** (download prints → dependency
  check → provider block → "entering tmux…" → express frame). Any timing
  drift lands the screenshot/hold mid-transition, and there's no
  per-stage knob to fix it — the pacing can only be tuned as one blob.
- **FontSize 16 vs the demo's 14** — the two GIFs don't look like the same
  product.
- (Assessment: net effect is 18 seconds that feel simultaneously rushed —
  the scroll — and dead — the hold.)

**The fix, in one line:** give it beats — a spoken premise, a paced
install, a *reveal* of the dark room, and a proof-of-life command — at the
demo GIF's typography.

## 2. Beat-by-beat (≤30s)

Terminal: **1080×620, FontSize 14, 20fps** — identical to the hero demo.
Captions are typed shell comments (they need no video editing and can't
lie about what's on screen). Total target **~27s**.

| # | t (target) | Action | What the viewer sees / learns |
|---|---|---|---|
| 0 | 0–3s | caption: `# fresh machine → working AI team, one line` | the premise |
| 1 | 3–6s | type the curl one-liner, Enter | the entire ask |
| 2 | 6–9s | (installer runs) | `installed ~/.local/bin/orchestrator (downloaded)` ×2 — visible receipts |
| 3 | 9–13s | (installer continues) | `providers:` block — the state lattice in the wild: e.g. `claude ready · codex ready · grok locked out` plus official install hints for anything missing. Honest, informative, no cherry-picking |
| 4 | 13–15s | (installer continues) | `entering tmux (session 'orchestrator') and running the express setup…` — **the installer self-captions the swap**; hold a beat so it can be read |
| 5 | 15–22s | (tmux swap → express frame) | **the reveal: the twelve-line dark room** — wordmark, provider states, `defaults locked`, `wrote …config.toml`, `customize → orchestrator init --custom`. Longest hold in the GIF; this is the centerpiece |
| 6 | 22–26s | type `orchestrator list` at the landed prompt | `no active teammates` — **proof of life**: we really are in a working, configured session |
| 7 | 26–29s | caption: `# you're in. spawn your first teammate.` | the handoff to the viewer |

Every beat legible without audio; stage-matched sleeps replace the single
10s blob so each seam can be tuned independently between takes.

## 3. Environment & preconditions

Recorded in the existing throwaway harness — `docs/recordings/
setup-install.sh` needs **no changes** (scratch HOME at `/tmp/demo`,
scratch `TMUX_TMPDIR`, never the operator's tmux server; safe to re-run):

- **Repo must be public** for the real-URL take (the raw one-liner 404s
  while private). Until then, use the documented private-repo mode:
  `python3 -m http.server 8123 --bind 127.0.0.1` from the repo root,
  `TEAMCTL_RAW_BASE=http://127.0.0.1:8123 ./setup-install.sh`, and point
  the tape's curl at the local URL. **Re-record with the real GitHub URL
  before shipping** — the typed line is part of the message.
- The `0<> "$TTYDEV"` tmux-bootstrap fix must be in the pinned revision
  (it is, post-v0.3.0 — the black-screen bug the old recording found).
- Provider states in the frame come from what the scratch HOME seeds plus
  which CLIs are on PATH. The default seeding (empty `~/.claude.json` +
  `~/.codex/auth.json`, nothing for grok) on a machine with all three CLIs
  installed yields **ready / ready / locked out** — three different states
  on screen, which quietly demos the v0.4.0 lattice. Verify the frame
  matches expectation on the first take; adjust seeding if the builder's
  lattice changes detection.
- Recording machine should already have tmux + python3 ≥3.11 (no
  dependency prompts in-frame; the offer flow is documented, not
  demoed — it would blow the 30s budget and needs sudo theater).
- Zero tokens: the installer and express setup call no provider.

## 4. Re-record procedure

```sh
cd docs/recordings
./setup-install.sh                    # fresh /tmp/demo every take
vhs install-v2.tape                   # writes ./install-v2.gif
# review: ≤30s, no type-ahead seams, express frame fully rendered and held,
# `orchestrator list` answered, file size well under 4MB
mv install-v2.gif ../assets/install.gif
```

Then restore the README embed (README-v2.md already carries it live, not
commented out — ship the GIF with, or before, that README).

## 5. Deliverable spec

- `docs/assets/install.gif` — 1080×620, 20fps, ~27s, expect ≤1MB (mostly
  stills; the old 20s take was smaller than the demo's 1.4MB).
- Alt text (in README-v2.md): one-liner → detection → landed in tmux with
  express setup done.
- Export a still of beat 5 (the dark room) — candidate for release notes
  and the Pages one-pager (see gif-placement-plan.md).
