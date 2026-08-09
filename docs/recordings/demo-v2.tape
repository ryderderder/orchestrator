# orchestrator hero demo v2 — one real task through ALL THREE providers:
# research -> grok, implementation -> claude, review -> codex, in parallel.
# REAL WORK: every teammate is the actual provider CLI editing/reading the
# seeded tinylog.py. Expect ~10-30k tokens per take across the three
# subscriptions (see demo-storyboard.md §5).
#
# Environment: build with ./setup-demo-live.sh <pushed-rev> first, then run
# the per-provider smoke tests (storyboard §6) BEFORE rolling.
# Pacing: blind timed pacing (vhs Wait is flaky inside tmux — see
# docs/recordings/README.md); the three `result --wait` calls self-sync on
# real provider latency, so variable turn times cannot desync the take.
# If a take lands 75-95s, uncomment PlaybackSpeed instead of cutting beats.
Output demo-v2.gif

Set Shell "bash"
Set FontSize 14
Set Width 1080
Set Height 620
Set Padding 16
Set TypingSpeed 30ms
Set Framerate 20
# Set PlaybackSpeed 1.25   # overrun valve only — keep 1.0 when a take fits

Hide
Type "source /tmp/teamhome-live/env.sh && clear"
Enter
Sleep 1s
Type "tmux -S /tmp/teamhome-live/tmux.sock -f /tmp/teamhome-live/tmux.conf new-session -s orchestrator -n lead"
Enter
Sleep 2s
Type "clear; tmux clear-history"
Enter
Sleep 1s
Show

# ---- beat 0: premise --------------------------------------------------------
Type "# one task: add --json to tinylog.py"
Sleep 300ms
Enter
Type "# one team: three AI subscriptions"
Sleep 300ms
Enter
Sleep 1.5s

# ---- beat 1: capacity is data ----------------------------------------------
Type "orchestrator usage"
Sleep 300ms
Enter
Sleep 4s

# ---- beat 2: the casting decision ------------------------------------------
Type "# cast: research->grok · build->claude · review->codex"
Sleep 300ms
Enter
Sleep 1.5s

# ---- beats 3-5: three dispatches, three panes, three vendors ----------------
Type `orchestrator dispatch researcher --provider grok --task 'Recommend a JSON schema for the --json flag of the log CLI tinylog.py in this directory (read it first). One object per entry. Return ONLY JSON: {"shape": {...}, "rationale": "<=25 words"}.'`
Sleep 300ms
Enter
Sleep 3s

Type "orchestrator dispatch builder --provider claude --model sonnet --task 'Add a --json flag to tinylog.py in this directory: one JSON object per log entry on stdout; default text output unchanged. Then print ONLY the unified diff of your change.'"
Sleep 300ms
Enter
Sleep 3s

Type `orchestrator dispatch reviewer --provider codex --effort low --task 'Read tinylog.py. List edge cases a new --json output flag must not break (empty file, malformed lines, etc). Return ONLY JSON: {"edge_cases": ["..."]} - max 5 items, <=12 words each.'`
Sleep 300ms
Enter
Sleep 3s

# ---- beat 6: the roster ------------------------------------------------------
Type "orchestrator list"
Sleep 300ms
Enter
Sleep 3s

# ---- beat 7: hold — let the viewer watch three CLIs work --------------------
Sleep 6s

# ---- beats 8-10: results come home (each --wait self-synchronizes) ----------
Type "orchestrator result researcher --wait"
Sleep 300ms
Enter
Sleep 5s

Type "orchestrator result reviewer --wait"
Sleep 300ms
Enter
Sleep 5s

Type "orchestrator result builder --wait"
Sleep 300ms
Enter
Sleep 7s

# ---- beat 11: synthesis ------------------------------------------------------
Type "# schema from grok · diff from claude · edge cases from codex — synthesized"
Sleep 300ms
Enter
Sleep 2s

# ---- beat 12: clean teardown (each shutdown needs ~4s) -----------------------
Type "for r in researcher builder reviewer; do orchestrator shutdown $r; done"
Sleep 300ms
Enter
Sleep 13s

# ---- beat 13: empty roster + pointer -----------------------------------------
Type "orchestrator list"
Sleep 300ms
Enter
Sleep 2s
Type "# your subscriptions, one team — github.com/ryderderder/orchestrator"
Sleep 300ms
Enter
Sleep 4s
