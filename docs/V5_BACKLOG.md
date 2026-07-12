# teamctl — v0.5+ backlog (from fresh-eyes product review, 2026-07-12)

Ranked by value ÷ effort. All competitor claims verified against live repos/docs during the review.

## v0.5 candidates (ranked)
1. **Git-worktree isolation per teammate** — highest value. Universal in the field
   (claude-squad, ccmanager, uzi, gwq, Conductor, container-use). Without it, parallel
   teammates collide on files → real team size ≈ 1 writer; the "never two teammates on one
   file" rule is currently enforced only by convention. Worktrees enforce it mechanically.
   Effort: medium (`--cwd` already threaded).
2. **Gemini CLI as 4th provider + pluggable-provider `agents.toml` escape hatch.** Gemini
   CLI: 106k★, Apache-2.0, `-p` + `--output-format json`, free Google-account quota tier —
   fits the "already-paid/free-quota" pitch better than grok. Custom-provider block kills the
   "why not my CLI?" objection class. Effort: low-medium. Possibly even before more lattice work.
3. **Teammate status detection (busy/waiting/idle) + notify hook.** ccmanager's headline
   feature; "which agent is silently blocked on a prompt" is the #1 multi-pane pain and a
   prerequisite for smarter routing. Effort: medium (poll capture-pane; pane-scraping already exists).
4. **Roster persistence / resurrect across reboots** — already owner-requested; KEEP, it's a
   moat: native Claude agent-teams cannot resume teammates (documented limitation);
   thurbox/Gastown sell reboot-survival. Reuse the exact-session resume machinery already built.
5. **Reactive fallback + wait-for-reset auto-resume** — quota goes stale mid-task; complements
   proactive routing. Effort: low-medium (exhaustion already classified in cmd_result).
6. **Rank route survivors by usage headroom, not just availability** — `route_select` currently
   ranks by preference order and only excludes exhausted providers; users expect "route to most
   headroom." Cheap: sort survivors by lowest used_percent. Effort: low.
7. **Merge/land step** (diff review → checkpoint/commit → optional PR). Pairs with #1. Effort: med-high.
8. **Shared task list with dependencies ("B after A")** — coordination spine; enables non-parallel
   work. Effort: high → v0.6+.

## Fine to leave parked (justified)
- Teammate↔teammate direct messaging — lead-mediated model is a defensible stance; don't apologize.
- Per-task cost attribution — in subscription-land, quota IS cost; usage scraping substitutes.
- Saved team templates — the `agents.toml` (#2) gives ~80% for free; defer standalone.
- Plan-approval/completion gates — matters more when fully headless; defer past v0.5.
- `--json` output mode for status commands — v0.5 nice-to-have; design the agent guide to absorb it.

## Positioning (verified)
- Claim "**first quota-aware ROUTER for subscription-CLI teams**," not "only tool that knows your
  quota" (scraping is commodity; the orchestration+routing combo is the moat).
- Compliance advantage: drives OFFICIAL vendor CLIs, doesn't impersonate a subscription
  (opencode removed Claude Pro/Max login in 1.3.0 citing Anthropic's prohibition). Never cross this line.

## Shipped/handled in v0.4.0 (not backlog)
- A1 role-name injection + path traversal fix (validate role `^[A-Za-z0-9][A-Za-z0-9._-]*$`).
- A2 installer first-run now enables lead mode (reversible: `teamctl lead off`); the closing
  frame shows a real spawn example + "you're in tmux, talk to your lead" orientation, and bare
  `teamctl` opens that lead chat.
- A3 the installer's "not on PATH" warning survives the tmux takeover — re-printed durably inside
  the express frame (`TEAMCTL_PATH_NOTE`), and the installer offers to append it to the shell profile.
- Auth-state lattice unifies vocabulary across init frame AND `providers`; real-auth probes
  (not `~/.claude.json` presence, which exists pre-login).

## Go-public checklist (do BEFORE flipping the repo public)
- **Ask GitHub Support to purge unreachable pre-scrub objects.** The 2026-07-12
  history rewrite (AI-attribution trailers + root-commit author normalization)
  cleaned every clonable ref, but GitHub still holds `refs/pull/1/*` server-side,
  pinning the pre-scrub commits — closing or deleting the PR does NOT remove it;
  only GitHub's own GC/Support purge can. Verify afterwards with an explicit
  `git fetch origin '+refs/pull/*:refs/remotes/pr/*'` + trailer/identity grep.
- Re-run the fresh-clone verification one last time at flip time: trailer grep 0
  across --all, identities only `ryderderder <ryder.wolf@pm.me>`, contributors
  API only ryderderder, CI green.
- Drop the "(private for now — ask me for auth, don't guess
  credentials)" line from the paste block in README.md AND
  docs/INSTALL_PROMPT.md (keep them byte-identical) — it is only
  true while the repo is private.
- Render + embed the launch GIFs (demo-v2, install-v2) and set the social-preview
  still per the gif-placement plan.
