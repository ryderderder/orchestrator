# orchestrator demo — lead pane orchestrating teammates: usage → route reasoning →
# two interactive spawns + one headless dispatch (shell provider: real tmux
# mechanics, zero tokens; neutral model labels) → result read-back → teardown.
# Runs entirely inside an isolated environment (see setup-demo.sh).
# Blind timed pacing throughout: vhs's Wait is flaky inside tmux (see the
# recordings README), and `result --wait` self-synchronizes the round-trip.
Output demo.gif

Set Shell "bash"
Set FontSize 14
Set Width 1080
Set Height 620
Set Padding 16
Set TypingSpeed 30ms
Set Framerate 20

Hide
Type "source /tmp/teamhome/env.sh && clear"
Enter
Sleep 1s
Type "tmux -S /tmp/teamhome/tmux.sock -f /tmp/teamhome/tmux.conf new-session -s orchestrator -n lead"
Enter
Sleep 2s
Type "clear; tmux clear-history"
Enter
Sleep 1s
Show

Type "orchestrator usage"
Sleep 300ms
Enter
Sleep 3s

Type "orchestrator route reviewer --task 'Review the release diff for regressions.' --dry-run"
Sleep 300ms
Enter
Sleep 3.5s

Type "orchestrator spawn code-reviewer --provider shell --model model-a"
Sleep 300ms
Enter
Sleep 2s

Type "orchestrator spawn researcher --provider shell --model model-b"
Sleep 300ms
Enter
Sleep 2s

Type `orchestrator dispatch analyst --provider shell --model model-c --task 'sleep 6; echo "{\"todos\": 4, \"hardest\": \"exact-session follow-ups\"}"'`
Sleep 300ms
Enter
Sleep 1.5s

Type "orchestrator list"
Sleep 300ms
Enter
Sleep 2.5s

Type "orchestrator result analyst --wait"
Sleep 300ms
Enter
Sleep 4.5s

Type "orchestrator shutdown code-reviewer"
Sleep 300ms
Enter
Sleep 4s

Type "orchestrator shutdown researcher"
Sleep 300ms
Enter
Sleep 4s

Type "orchestrator shutdown analyst"
Sleep 300ms
Enter
Sleep 3s

Type "orchestrator list"
Sleep 300ms
Enter
Sleep 4s
