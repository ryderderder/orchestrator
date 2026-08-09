# orchestrator install — the real one-liner in a clean throwaway HOME (see
# setup-install.sh): downloads, dependency/provider detection, tmux bootstrap,
# express setup card. Blind timed pacing (vhs Wait is flaky inside tmux).
# PRECONDITIONS for the final take:
#   - repo public (raw.githubusercontent.com reachable anonymously)
#   - install.sh tmux bootstrap fix (0<> "$TTYDEV") pushed to main
#   - /tmp/demo rebuilt via setup-install.sh, NO TEAMCTL_RAW_BASE override
Output install.gif

Set Shell "bash"
Set FontSize 16
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

Type "curl -fsSL https://raw.githubusercontent.com/ryderderder/orchestrator/main/install.sh | bash"
Sleep 800ms
Enter

# downloads (2 files from GitHub) + "entering tmux…" + express setup card
Sleep 10s
Screenshot install-final-check.png

# hold on the summary card so it can be read
Sleep 8s
