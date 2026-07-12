# Install teamctl via your AI agent

Paste the block below into any AI coding CLI — Claude Code, Codex, Grok,
Gemini, or similar. The prompt is a pointer, not a manual: the repo's own
docs carry the instructions, and your agent reads them first.

```text
Install teamctl for me — https://github.com/ryderderder/teamctl
(it runs AI teammates — Claude Code / Codex / Grok / Gemini CLIs — as tmux panes).

1. Orient first — read these from the repo (main branch):
   README.md · docs/AGENT_GUIDE.md · llms.txt
2. Install:
   curl -fsSL https://raw.githubusercontent.com/ryderderder/teamctl/main/install.sh | bash -s -- --no-init
   Essentials: ask me before anything that needs sudo; never install a
   provider CLI without asking; make sure ~/.local/bin is on my PATH.
3. Configure: run `teamctl init` (zero questions) and show me its summary.
4. Verify: run `teamctl doctor` and show me the output.
5. Tell me my controls: `teamctl settings` · `teamctl lead on|off|status` ·
   `teamctl uninstall` (run `teamctl lead off` first).
```
