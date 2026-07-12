# Install teamctl via your AI agent

Paste everything inside the block below into any AI coding CLI — Claude
Code, Codex, Grok, or similar — and it will set teamctl up for you, end to
end.

```text
Install teamctl (https://github.com/ryderderder/teamctl) for me — it manages
AI teammates (Claude Code / Codex / Grok CLIs) as tmux panes. Do all of the
following, in order:

1. Run the installer:
     curl -fsSL https://raw.githubusercontent.com/ryderderder/teamctl/main/install.sh | bash -s -- --no-init
   (--no-init because you are driving the setup yourself; without it the
   installer enters tmux and runs the express setup). If it reports missing
   dependencies (tmux, or python3 older than 3.11), install them with the
   system package manager (ask me before anything that needs sudo). If it
   reports no provider CLI, show me the official install one-liners it
   prints and ask which (if any) to run. Make sure ~/.local/bin is on my
   PATH; fix my shell profile if not.

2. Configure it: run `teamctl init` (the express setup — zero questions;
   it detects providers, writes sane defaults, and prints a compact
   summary). Show me that summary, and tell me I can run
   `teamctl init --custom` (rich arrow-key wizard) or
   `teamctl config --menu` any time to change it. Express uses the
   detected provider order for routing; if I want a different order, set
   it with `teamctl config routing.preference ...` — never pick it for me.

3. Offer me lead mode: explain that `teamctl lead on` installs a manager
   identity into every detected agent CLI's global instructions file
   (plus a skill and a recommended per-prompt reminder hook for Claude
   Code — mechanisms the other CLIs don't have), all reversible with
   `teamctl lead off`. Run it if I say yes.

4. Verify your work: run `teamctl doctor` (a health check — python, tmux,
   provider sign-in states, config, statusline, install source), plus
   `teamctl --version` and `teamctl providers`, and show me the output.

5. Report what you did, what you skipped and why, and finish by telling me
   my controls:
     - from the shell: `teamctl settings` (or `teamctl config --menu`) to
       adjust preferences, `teamctl lead on|off|status` for the lead
       identity, `teamctl uninstall` (`teamctl lead off` first) to undo
       everything.
     - from a chat: with lead mode on, I can just say "open the teamctl
       menu" to any lead agent and it will present and apply my settings.
```
