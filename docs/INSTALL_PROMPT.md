# Install teamctl via your AI agent

Paste the block below into any AI coding CLI — Claude Code, Codex, Grok,
Gemini, or similar. The prompt is a pointer, not a manual: the repo's own
docs carry the instructions, and your agent reads them first.

```text
Install teamctl for me — https://github.com/ryderderder/teamctl
(runs Claude Code / Codex / Grok / Gemini / Antigravity agy
 as tmux panes)
Get it and install (--no-init skips the tmux takeover):
  curl -fsSL https://raw.githubusercontent.com/ryderderder/teamctl/main/install.sh | bash -s -- --no-init
(private for now — if that 404s, ask me for access, then
 clone the repo and run: bash install.sh --no-init)
Then read README.md, docs/AGENT_GUIDE.md, and llms.txt to
drive it; verify with teamctl doctor. Ask before anything sudo.
```
