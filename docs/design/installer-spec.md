I'll ground the design in Orchestrator's current setup flow and CLI voice, then write a copy-ready spec with exact ASCII mockups for Express and Custom.# Orchestrator Setup Experience — Design Spec

**Status:** implementable  
**Surfaces:** `orchestrator init` (default = Express), `orchestrator init --custom` / mid-Express “customize” path  
**Runtime:** pure terminal; primary path = stdlib `curses`; fallback = plain `input()` prompts  
**Canvas (Custom):** 100×30 tmux pane (design at 100 cols × 30 rows; clip gracefully if smaller)  
**Tone:** dark, atmospheric, confident — Grok Build energy, zero SaaS onboarding

---

## 0. Product intent

The current wizard is a **serial questionnaire**: detect → per-provider model → per-provider effort → routing order → verbosity → delegation → three optional Y/N integrations → long summary. It feels like a form, not a tool.

**New contract**

| Path | Questions | Feel | Exit |
|------|-----------|------|------|
| **Express** (default) | 0 | A *moment* — ~12–18 lines, then the shell | Ready to `spawn` / `dispatch` |
| **Custom** | Arrow-key TUI, ≤3 screens | Tight cockpit, not a wizard | Same config + optional toggles |
| **`--yes`** | 0 (scripted) | Machine-readable; no chrome | Config only (existing semantics) |
| **Degrade** | Plain prompts | If no TTY / no curses / `TERM=dumb` | Functional, not pretty |

**Express defaults (locked without asking)**

| Key | Value | Rationale |
|-----|-------|-----------|
| `routing.preference` | available providers, **alphabetical** | Existing `--yes` behavior; documented as arbitrary, not a ranking |
| `providers.*.model` | empty | CLI’s own default; orchestrator never invents model ids |
| `providers.*.effort` | `"high"` | Matches README example config |
| `output.verbosity` | `"normal"` | Safe middle |
| `lead.delegation` | `"ask"` | Existing product default |
| Optional integrations (tmux / statusline / lead) | **off** | Opt-in only; Custom screen 3 or later `orchestrator lead on` |

**Non-goals:** emoji, spinners that need unicode fonts beyond ASCII+box-drawing, multi-page essays, “Welcome to the Orchestrator family.”

---

## 1. Shared visual system

### 1.1 256-color palette (dark terminals)

Use `curses.init_pair` + `curses.use_default_colors()` so background stays the user’s terminal black.

| Role | 256 code | Typical use |
|------|----------|-------------|
| **fg_primary** | `252` | Body copy, list labels |
| **fg_dim** | `240` | Hints, secondary meta, unselected chrome |
| **fg_mute** | `236` | Faint rules, progress track empty |
| **fg_accent** | `51` | Wordmark, focus accent, “ready”, active step |
| **fg_accent_soft** | `44` | Secondary highlight (section titles) |
| **fg_warn** | `180` | Installed-not-authed, missing optional |
| **fg_bad** | `167` | Not found / not on PATH |
| **fg_ok** | `114` | Locked-in / wrote / confirm success |
| **fg_inverse** | `232` | Text on selection bar |
| **bg_select** | `51` | Selection bar fill (fg = `232`) |
| **bg_bar_idle** | `236` | Unselected list row hover optional |
| **border** | `238` | Box edges |
| **title** | `255` | Screen titles (rare; mostly accent) |

**Express** (no curses): same palette via ANSI `\033[38;5;Nm` when `sys.stdout.isatty()` and `TERM` not dumb; else plain monochrome.

**Degrade rule:** if 256-color fails, drop to reverse-video for selection and default fg/bg only. Never require truecolor.

### 1.2 Box-drawing set (stdlib-safe)

Prefer **light single-line** Unicode box-drawing (UTF-8 terminals). ASCII fallback when `locale` / encoding is not UTF-8.

| Element | UTF-8 | ASCII fallback |
|---------|-------|----------------|
| Horizontal | `─` (U+2500) | `-` |
| Vertical | `│` (U+2502) | `\|` |
| Corners | `┌┐└┘` | `+` |
| Tees | `├┤┬┴` | `+` |
| Cross | `┼` | `+` |
| Heavy rule (wordmark underline only) | `━` (U+2501) | `=` |
| Ellipsis row | `…` | `...` |
| Route chevron | `›` | `>` |
| Bullet (status) | `·` (U+00B7) | `*` |
| Selection marker | `›` left of row **or** full reverse bar | `>` |

**Do not use:** double-line boxes, rounded corners (`╭`), block elements that look like a progress bar library, or mixed styles in one frame.

### 1.3 Cursor / selection affordances

| Context | Affordance |
|---------|------------|
| List (models, enums) | Full-width selection bar: `bg_select` + `fg_inverse`; leading `›` in accent |
| Multi-toggle | `[x]` / `[ ]` in accent when focused; space/enter flips |
| Text entry (custom model id) | Underscore caret `_` blinking if `curses.A_BLINK` available; else static `█` or `_` |
| Disabled / unavailable | dim `fg_dim`, no selection bar on that row |
| Focus leave | bar off; dim reappears |

### 1.4 Progress (Custom only)

Top chrome, fixed:

```
  orchestrator  ·  custom
  1 models ── 2 posture ── 3 seal
         ^ current in fg_accent; done steps fg_ok; future fg_dim
```

Step labels are short verbs, not “Step 1 of 3.” Active step is the only accented one. No percentage counters.

### 1.5 Motion budget (Express)

Optional, **TTY only**, total wall clock ≤ ~1.2s:

1. Wordmark alone (80–120ms pause)  
2. Provider lines appear one-by-one (≤80ms each)  
3. Defaults block appears as a unit  
4. Write line + customize hint  

If `NO_COLOR`, `TEAMCTL_PLAIN=1`, or non-TTY: print final frame only, no delays.

---

## 2. Voice

**Register:** confident, terse, a little moody. Never cutesy, never corporate, never apologetic.

### 2.1 Microcopy bank (use as-is or near-as-is)

1. `scanning the dark for providers`  
2. `ready` / `quiet` / `locked out` / `not installed` — status words (the v0.4.0 provider state lattice; never “available / not authenticated”)  
3. `defaults locked`  
4. `nothing to configure. yet.`  
5. `pick a model — or leave the CLI its secrets`  
6. `how hard should they think`  
7. `how loud should we be`  
8. `when does the lead hand work away`  
9. `seal it`  
10. `wrote the map` → path  
11. `customize later: orchestrator init --custom`  
12. `no tty. plain path.` (degrade banner)

**Avoid:** “Great choice!”, “You’re all set 🎉”, “Let’s get you onboarded”, “Almost there!”, exclamation spam.

**Status word map** *(v0.4.0 amendment — the provider state lattice)*

The original spec had one word (`quiet`) for both “not on PATH” and
“signed in but silent”, and the first real install read that as breakage:
three different truths, one ambiguous label. Since v0.4.0 every surface
(this frame, `providers`, `usage`, the installer screen) uses one word
per truth:

| Detection | Word | Color |
|-----------|------|-------|
| installed + signed in + usage numbers known | `ready` | `fg_ok` |
| installed + signed in, no usage numbers yet | `quiet` — with the dim inline hint `— signed in, wakes on first use` | `fg_soft` |
| on PATH, not signed in | `locked out` | `fg_warn` |
| not on PATH | `not installed` | `fg_dim` |
| auth artifacts unreadable | `unknown` | `fg_dim` |

`quiet` and `ready` are equally usable: usage data changes the word, not
the eligibility (both are configured and routed). Signed-in detection is
content-validated against each CLI's own login artifacts — see the README
“Provider states” table.

---

## 3. Flow A — EXPRESS SETUP

### 3.1 Entry

```
orchestrator init              # Express
orchestrator init --yes        # scripted: no chrome, config-only (keep)
orchestrator init --custom     # jump Custom
```

Express is the default when stdin/stdout is a TTY. No mode picker.

### 3.2 Behavior (zero questions)

1. Detect `claude` / `codex` / `grok` (installed + auth).  
2. Build `providers_cfg` for **ready** only: `model=""`, `effort="high"`.  
3. `preference = sorted(ready)`.  
4. Write `~/.config/agent-team/config.toml` (backup existing → `config.toml.bak-orchestrator`).  
5. Print Express frame.  
6. Exit 0. Do **not** offer tmux/statusline/lead in Express.

If **zero** providers usable: still write a minimal config (verbosity + delegation only), show the frame with the honest per-provider words, and one extra dim line — `log a provider in, then re-run` when something is `locked out`, else `install a provider CLI, then re-run`.

### 3.3 Exact mockup — happy path (1 ready, 1 quiet, 1 not installed)

**Line budget:** 16 content lines (within 12–18).  
**Width:** keep ≤ 56 cols for the moment; rest of terminal stays empty (breathing room).

```text
            t e a m c t l
         ━━━━━━━━━━━━━━━━━

  · claude      ready
  · codex       quiet — signed in, wakes on first use
  · grok        not installed

  defaults locked
    route     claude › codex
    model     (cli default)
    effort    high
    voice     normal
    lead      ask

  wrote  ~/.config/agent-team/config.toml

  customize →  orchestrator init --custom
```

### 3.4 Exact mockup — all three ready

```text
            t e a m c t l
         ━━━━━━━━━━━━━━━━━

  · claude      ready
  · codex       ready
  · grok        ready

  defaults locked
    route     claude › codex › grok
    model     (cli default)
    effort    high
    voice     normal
    lead      ask

  wrote  ~/.config/agent-team/config.toml

  customize →  orchestrator init --custom
```

### 3.5 Exact mockup — nothing installed

```text
            t e a m c t l
         ━━━━━━━━━━━━━━━━━

  · claude      not installed
  · codex       not installed
  · grok        not installed

  defaults locked
    route     —
    model     (cli default)
    effort    high
    voice     normal
    lead      ask

  wrote  ~/.config/agent-team/config.toml
  install a provider CLI, then re-run

  customize →  orchestrator init --custom
```

### 3.6 Exact mockup — installed, not signed in

```text
            t e a m c t l
         ━━━━━━━━━━━━━━━━━

  · claude      locked out
  · codex       ready
  · grok        not installed

  defaults locked
    route     codex
    model     (cli default)
    effort    high
    voice     normal
    lead      ask

  wrote  ~/.config/agent-team/config.toml

  customize →  orchestrator init --custom
```

### 3.7 ANSI sketch (implementer reference)

```
wordmark:     ESC[38;5;51m  + letter-spaced "t e a m c t l" + ESC[0m
rule:         ESC[38;5;238m + "━━━━━━━━━━━━━━━━━" + ESC[0m
bullet:       ESC[38;5;240m "·" ESC[0m
ready:        ESC[38;5;114m ready ESC[0m
quiet:        ESC[38;5;44m quiet ESC[0m  + dim inline hint ESC[38;5;240m — signed in, wakes on first use ESC[0m
locked out:   ESC[38;5;180m locked out ESC[0m
not installed: ESC[38;5;240m not installed ESC[0m
section:      ESC[38;5;252m defaults locked ESC[0m
keys:         ESC[38;5;240m route/model/... ESC[0m
values:       ESC[38;5;252m ... ESC[0m
wrote:        ESC[38;5;114m wrote ESC[0m + path dim
hint:         ESC[38;5;240m customize →  ESC[38;5;44m orchestrator init --custom ESC[0m
```

### 3.8 Spacing rules (copy exactly)

- 1 blank line above wordmark (from previous shell prompt).  
- Wordmark centered in a 25-col field starting at column 12 (or: 12 spaces + wordmark).  
- 1 space indent before `·` provider rows.  
- 1 blank line between provider block and `defaults locked`.  
- Defaults keys left-aligned in a 10-char field (`route    `, `model    `, …) after 4-space indent.  
- 1 blank line before `wrote`.  
- 1 blank line before customize hint.  
- No trailing “Summary of changes” essay in Express. (Revert path: file backup name only if re-running overwrites; print only if backup was made: dim line `prior config → config.toml.bak-orchestrator` under `wrote`.)

### 3.9 Optional mid-frame (scan) — not required if plain dump preferred

If implementing the “moment” delay, intermediate frame (overwrite with final; do not leave in scrollback if possible — use `\r`/clear only within reserved block, or accept append-only final frame only):

```text
            t e a m c t l
         ━━━━━━━━━━━━━━━━━

  scanning the dark for providers
```

Then replace with final frame. Prefer **final frame only** if scrollback pollution is a concern; the static final mockup already sells the moment.

---

## 4. Flow B — CUSTOM MODE (curses TUI)

### 4.1 Constraints

| Constraint | Spec |
|------------|------|
| Library | `curses` only (stdlib) |
| Pane | Design for **100×30**; min usable **80×24** |
| Screens | **3 max**: Models → Posture → Seal |
| Input | ↑↓ navigate, Enter select/advance, Space toggle, `e` edit custom model, Esc/q back or quit with confirm on dirty |
| Exit write | Only on Seal → Confirm |
| Escape hatch | `p` plain prompts (tears down curses, runs degrade path) |

### 4.2 Screen map

```
  [1] MODELS     per ready provider: pick discovered id or "custom…"
  [2] POSTURE    effort (per provider or global) · verbosity · delegation · route order
  [3] SEAL       optional toggles + review strip + write
```

**Routing order on screen 2:** when ≥2 ready providers, a compact reorder list (↑↓ move focus, `<`/`>` or `h`/`l` swap with neighbor). Alphabetical default pre-selected.

**Effort:** one list applied to all ready providers in Express→Custom upgrade; Custom allows “same for all” (default) to keep screen count at 3. Optional advanced: tab between providers only if time; **v1 ships global effort** to stay at 3 screens.

### 4.3 Screen 1 — Model picker

**Purpose:** choose default model per ready provider; empty = CLI default.

**Layout regions (100×30):**

```
rows 0-1   header + progress
row  2     blank
row  3     section title
row  4     blank
rows 5-20  scrollable list (provider headers + model rows)
rows 21-22 blank / status
rows 23-28 help chrome
row  29    footer keys
```

#### Mockup — Screen 1 (exact)

```text
orchestrator  ·  custom                                                    100 cols →
1 models ── 2 posture ── 3 seal

  pick a model — or leave the CLI its secrets

  codex
  › gpt-5.3-codex                                          [selected bar]
    o3
    o4-mini
    custom…

  claude
    opus
    sonnet
    haiku
    custom…

  grok
    (provider default)
    custom…

  · discovered via orchestrator models · ids pass through verbatim

  ↑↓ move   enter choose   tab next provider   n next   p plain   q quit
```

**Selection bar:** entire content row 2–98 filled with `bg_select`/`fg_inverse`; leading `›` in column 2.

**Provider headers:** `fg_accent_soft`, not selectable.

**`(provider default)`** row: first row under each provider when no discovery, or always available as top choice (value `""`).

**`custom…`:** Enter → inline edit on that row:

```text
  › custom:  grok-4.5_                              ↵ commit  esc cancel
```

#### Model list rules

- Source: existing `discover_models(prov)` best-effort.  
- Cap visible discoveries to ~8 per provider; if more, `… N more` dim row (Enter = jump to custom).  
- Never invent ids not returned by discovery except free-typed custom.

---

### 4.4 Screen 2 — Effort / verbosity / delegation (+ route)

**Purpose:** three enum pickers + optional route order. One screen, no nested wizards.

#### Mockup — Screen 2 (exact)

```text
orchestrator  ·  custom
1 models ── 2 posture ── 3 seal

  how hard · how loud · when to hand off

  effort                                          [global for all ready]
  › high
    medium
    low
    xhigh                                         # show only if provider set supports; else omit

  voice
    terse
  › normal
    detailed

  lead
  › ask          — check once per session
    always       — hand off non-trivial work
    manual       — only when told

  route                                          # only if ≥2 ready
  › 1  codex
    2  claude
    3  grok
  · h/l or </> swap · order is yours, not ours

  ↑↓ section/item   enter open   n next   b back   p plain   q quit
```

**Interaction pattern (compact, no third axis of screens):**

- ↑↓ moves a **flat focus list**: effort values, then voice values, then lead values, then route rows.  
- Section headers are non-focusable.  
- Dim one-line gloss only on the focused lead row (shown in mockup as `— …`).  
- Route: focus a row, `h`/`l` or `</>` swaps with neighbor; numbers re-render.

**Visual:** only the focused enum value gets the selection bar. Current committed choice (even when unfocused) gets a dim `*` in column 1 or accent text without bar.

---

### 4.5 Screen 3 — Toggles + confirm (seal)

**Purpose:** optional integrations + review + single write action.

#### Mockup — Screen 3 (exact)

```text
orchestrator  ·  custom
1 models ── 2 posture ── 3 seal

  seal it

  review
    route     codex › claude › grok
    codex     gpt-5.3-codex · high
    claude    opus · high
    grok      (cli default) · high
    voice     normal
    lead      ask

  extras                                                 [off by default]
  [ ]  tmux borders          pane labels · role · model
  [ ]  claude statusline     model · effort · ctx%
  [ ]  lead mode             manager identity for agent CLIs
  [ ]  lead hook             per-prompt reminder (claude only)

  ›  write config
     abort

  · backups first · extras default off · re-run anytime

  ↑↓  space toggle  enter run  b back  p plain  q quit
```

**Write config** focused by default on entry to screen 3 (fast path).  
**abort** = exit 0 without write (or restore: if no write yet, just quit).

On successful write, tear down curses and print a **short post-frame** (reuse Express voice, not the old multi-page summary):

```text
  wrote the map
    ~/.config/agent-team/config.toml

  from here
    orchestrator providers
    orchestrator spawn reviewer --provider codex
    orchestrator settings
```

If extras installed, append one line each, still terse:

```text
  + tmux block     source: tmux source-file ~/.tmux.conf
  + statusline     orchestrator statusline (Claude Code)
  + lead mode      orchestrator lead status
```

No multi-line revert essay; mention: `revert notes: orchestrator lead off · backups *.bak-orchestrator`.

---

### 4.6 Full 100×30 “developer copy” — Screen 1 frame

Use this as the canonical curses paint target (spaces matter; `|` = edge guides only in this doc — **do not paint the outer `|`**).

```text
+--------------------------------------------------------------------------------------------------+
|orchestrator  ·  custom                                                                                |
|1 models ── 2 posture ── 3 seal                                                                   |
|                                                                                                  |
|  pick a model — or leave the CLI its secrets                                                     |
|                                                                                                  |
|  codex                                                                                           |
|  › gpt-5.3-codex                                                                                 |
|    o3                                                                                            |
|    o4-mini                                                                                       |
|    custom…                                                                                       |
|                                                                                                  |
|  claude                                                                                          |
|    opus                                                                                          |
|    sonnet                                                                                        |
|    haiku                                                                                         |
|    custom…                                                                                       |
|                                                                                                  |
|  · discovered via orchestrator models · ids pass through verbatim                                     |
|                                                                                                  |
|                                                                                                  |
|                                                                                                  |
|                                                                                                  |
|                                                                                                  |
|                                                                                                  |
|                                                                                                  |
|                                                                                                  |
|↑↓ move   enter choose   tab next provider   n next   p plain   q quit                            |
+--------------------------------------------------------------------------------------------------+
```

(Rows intentionally sparse: empty lower half is **feature**, not missing content.)

---

## 5. Degrade path (plain prompts)

Trigger: not a TTY, `curses.error` on init, `TERM` in (`dumb`, `unknown`), or user hits `p`.

**Shape:** few prompts, same defaults as Express, optional overrides — **not** the old per-field wall.

```text
orchestrator init — plain path

  claude  ready
  codex   ready
  grok    quiet

  model per provider [enter = cli default]
  codex: 
  claude: 

  effort [high]: 
  voice  [normal]: 
  lead   [ask]: 
  route  [codex,claude]: 

  write ~/.config/agent-team/config.toml? [Y/n] 
```

No tmux/statusline/lead prompts here unless `TEAMCTL_INIT_EXTRAS=1` (env escape for power users). Point to `orchestrator lead on` instead.

---

## 6. Implementation map (for the developer)

### 6.1 Suggested module boundaries (single-file ok)

| Piece | Responsibility |
|-------|----------------|
| `express_init()` | detect → defaults → write → print frame |
| `custom_init()` | curses wrapper; state object; 3 screens |
| `plain_init()` | degrade prompts |
| `InitState` | providers_cfg, preference, verbosity, delegation, extras flags |
| `paint_header(stdscr, step)` | progress chrome |
| `list_widget(...)` | selection bar, scroll |
| existing `_render_config` / `_detect_providers` / `discover_models` | reuse |

### 6.2 Keybinds (Custom)

| Key | Action |
|-----|--------|
| `↑` `↓` / `k` `j` | move |
| `Enter` | select / advance primary |
| `Space` | toggle checkbox |
| `n` | next screen (validate) |
| `b` / `Esc` | back (Esc on screen 1 = quit confirm) |
| `Tab` | next provider block (screen 1) |
| `h` `l` / `<` `>` | swap route order (screen 2) |
| `e` | edit custom model when on `custom…` |
| `p` | plain path |
| `q` | quit (confirm if dirty) |

### 6.3 Validation

- Unknown verbosity/delegation → snap to default, dim flash message `snapped to normal` / `snapped to ask`.  
- Empty custom model → treat as provider default.  
- Route must be permutation of ready set; drop unknowns silently (existing behavior).

### 6.4 Tests (behavior, not pixels)

- Express with 0/1/2+ providers writes expected TOML.  
- Express never prompts (scripted stdin empty).  
- Custom state → `_render_config` golden strings.  
- Plain path accepts blanks → Express defaults.  
- `--yes` unchanged.

---

## 7. Acceptance criteria

**Express**

- [ ] Zero interactive questions on TTY default path  
- [ ] Final output **12–18 lines** (count non-empty + intentional blanks as in mockups)  
- [ ] Wordmark + rule + providers + defaults + wrote + single customize line  
- [ ] No optional integration prompts  
- [ ] Feels intentional when scrolled in a dark terminal (not a log dump)

**Custom**

- [ ] ≤3 screens in 100×30  
- [ ] Model list from discovery + `custom…` + provider default  
- [ ] Effort, verbosity, delegation, route on one posture screen  
- [ ] Seal screen: review + off-by-default extras + write  
- [ ] Palette uses documented 256 codes; selection is a bar, not a lone `>`  
- [ ] `p` and non-TTY degrade without crash  

**Voice**

- [ ] No emoji spam  
- [ ] Status words: `ready` / `quiet` / `locked out`  
- [ ] Customize hint exactly: `customize →  orchestrator init --custom` (Express)

---

## 8. Appendix — side-by-side emotional target

| Old | New |
|-----|-----|
| “orchestrator init — set up defaults and optional integrations.” | wordmark silence, then status |
| Per-provider mini-interrogation | Express: none; Custom: one model list |
| Long delegation essay mid-prompt | One line gloss on focus |
| Three optional Y/N after config | Extras only on Seal, all off |
| Multi-bullet summary + controls footer | `wrote the map` + three commands |

---

## 9. One-line product statement (for PR / README)

> **`orchestrator init` is a twelve-line dark room that finds your providers and locks sane defaults; `--custom` is a three-screen cockpit if you want to aim.**

---

*End of spec. Mockups above are copy-source for implementers; prefer final Express frame byte-stable across versions so muscle memory holds.*