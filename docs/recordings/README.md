# README recordings — how to (re-)render

The README GIFs are rendered deterministically from
[vhs](https://github.com/charmbracelet/vhs) tapes in this directory
(`brew install vhs` — brings `ttyd` and `ffmpeg`). Every take runs in a
throwaway environment built by the setup scripts: scratch `$HOME`s under
`/tmp`, tmux on its own socket/server, `TEAMCTL_STATE` pointed at scratch —
the operator's real config, state, and tmux server are never touched.

## Render the demo GIF

```sh
cd docs/recordings
./setup-demo.sh <pushed-revision>   # fresh isolated env; pins orchestrator to that rev
vhs demo.tape                       # writes ./demo.gif (~50s, ~1.4MB)
mv demo.gif ../assets/demo.gif
```

Always re-run `setup-demo.sh` before a take (teammate state must be fresh),
and always pin a revision — the working tree may be someone's WIP.
What the tape shows: `usage` (real codex numbers via read-only symlinks) →
`route --dry-run` selection reasoning → two interactive spawns + one headless
`dispatch` (all `--provider shell`: real tmux/pane/handoff mechanics, **zero
tokens**, neutral `model-a/b/c` labels) → `list` → `result --wait` reading the
JSON answer back → three shutdowns → empty `list`.

## Render the install GIF

```sh
cd docs/recordings
./setup-install.sh                  # fresh throwaway HOME at /tmp/demo
vhs install.tape                    # writes ./install.gif
mv install.gif ../assets/install.gif
```

While the repo is **private**, the public one-liner 404s; record the same
download code path against a local server instead:

```sh
(cd ../.. && python3 -m http.server 8123 --bind 127.0.0.1 &)
TEAMCTL_RAW_BASE=http://127.0.0.1:8123 ./setup-install.sh
# and change the tape's Type line to:
#   curl -fsSL http://127.0.0.1:8123/install.sh | bash
```

Re-record with the real GitHub URL before shipping the GIF publicly.
Once `install.gif` exists, restore its embed in the top-level README (the
commented-out line under the install paragraph).

## Hard-won facts (read before debugging a take)

- **vhs `Wait` is flaky inside tmux.** `Wait+Screen /regex/` intermittently
  times out even though the pane demonstrably contains the text
  (`capture-pane` proves it) — the vhs-side screen stalls at different
  points across runs. Both tapes therefore use **blind timed pacing**
  (generous `Sleep`s; `result --wait` self-synchronizes) — after changing a
  tape, always eyeball the rendered GIF for type-ahead artifacts (fragments
  of the next command echoed before the previous prompt returned) and widen
  the preceding `Sleep` if you see them. `shutdown` needs ~4s.
- **tmux needs a read-write tty fd.** A tmux client whose terminal fd was
  opened read-only (`< "$TTYDEV"`) attaches with the right size but never
  renders one byte of UI — that was the install.sh black-screen bug (fixed
  with `0<> "$TTYDEV"`). Repro/verify without a terminal: run the command on
  a Python pty (`pty.openpty()` + `preexec_fn` doing `os.setsid()` +
  `fcntl.ioctl(slave, termios.TIOCSCTTY, 0)`, then read the master with a
  timeout) — the read-only variant emits ~46 bytes, the `0<>` variant emits
  the full escape-sequence UI stream.
- **Login-shell PATH resets break Orchestrator's config.** tmux launches
  default-shell as a *login* bash; on macOS `/etc/profile`'s `path_helper`
  reorders PATH so `/usr/bin/python3` (3.9 — no `tomllib`) shadows homebrew,
  and Orchestrator then silently ignores `config.toml` (e.g. `route` falls back
  to alphabetical order). The scratch rc files re-pin PATH; keep that line.
- **Never trust `TMUX_TMPDIR` for isolation when `$TMUX` is set** (e.g. when
  driving takes from inside an agent's tmux pane): tmux follows `$TMUX`
  straight to the real server. The setup scripts `unset TMUX TMUX_PANE` in
  the sandbox env and every tmux invocation in the tapes uses an explicit
  `-S /tmp/…/tmux.sock`.
- Keep GIFs ≤ ~4MB: 1080px wide, 20fps, ~50s ≈ 1.4MB with these tapes.
