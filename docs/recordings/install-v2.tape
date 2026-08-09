# orchestrator install v2 — cold machine -> one line -> the twelve-line dark
# room -> proof of life. Beat design in install-storyboard.md.
# PRECONDITIONS for the final take:
#   - repo public (raw.githubusercontent.com reachable anonymously) —
#     private-repo takes: serve the checkout locally and retype the curl
#     line against TEAMCTL_RAW_BASE (see storyboard §3)
#   - pinned revision includes the 0<> "$TTYDEV" tmux bootstrap fix
#   - /tmp/demo rebuilt via setup-install.sh immediately before the take
#   - recording machine has tmux + python3>=3.11 (no dep prompts in-frame)
# Blind timed pacing (vhs Wait is flaky inside tmux); sleeps are per-stage —
# tune the one that seams, not one 10s blob. Zero tokens are spent.
Output install-v2.gif

Set Shell "bash"
Set FontSize 14
Set Width 1080
Set Height 620
Set Padding 16
Set TypingSpeed 25ms
Set Framerate 20

Hide
Type "source /tmp/demo/env.sh && clear"
Enter
Sleep 1s
Show

# ---- beat 0: premise ---------------------------------------------------------
Type "# fresh machine -> working AI team, one line"
Sleep 300ms
Enter
Sleep 2s

# ---- beat 1: the entire ask --------------------------------------------------
Type "curl -fsSL https://raw.githubusercontent.com/ryderderder/orchestrator/main/install.sh | bash"
Sleep 800ms
Enter

# ---- beats 2-3: receipts + provider lattice (installer output, paced) --------
# downloads print ~immediately; provider block follows. Tune these two
# sleeps against real network on take 1.
Sleep 4s
# hold on the providers: block + install hints so the states can be read
Sleep 4s

# ---- beat 4: the installer self-captions the swap ----------------------------
# "entering tmux (session 'orchestrator') and running the express setup…"
Sleep 2s

# ---- beat 5: THE REVEAL — the twelve-line dark room ---------------------------
# tmux swap + express frame render, then the long hold. This is the
# centerpiece; do not trim below 6s.
Sleep 7s
Screenshot install-v2-darkroom.png

# ---- beat 6: proof of life in the landed session ------------------------------
Type "orchestrator list"
Sleep 300ms
Enter
Sleep 2.5s

# ---- beat 7: handoff ----------------------------------------------------------
Type "# you're in. spawn your first teammate."
Sleep 300ms
Enter
Sleep 3.5s
