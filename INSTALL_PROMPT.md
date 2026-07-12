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
   installer opens an interactive tmux wizard). If it reports missing
   dependencies (tmux, or python3 older than 3.11), install them with the
   system package manager (ask me before anything that needs sudo). If it
   reports no provider CLI, show me the official install one-liners it
   prints and ask which (if any) to run. Make sure ~/.local/bin is on my
   PATH; fix my shell profile if not.

2. Configure it: run `teamctl init` interactively if you have a terminal
   for me to answer prompts; otherwise run `teamctl init --yes` and tell me
   I can re-run `teamctl init` or use `teamctl config --menu` later. The
   wizard asks for MY provider routing order — never pick it for me.

3. Offer me lead mode: explain that `teamctl lead on` installs a manager
   identity into every detected agent CLI's global instructions file
   (plus a skill and a recommended per-prompt reminder hook for Claude
   Code — mechanisms the other CLIs don't have), all reversible with
   `teamctl lead off`. Run it if I say yes.

4. Verify your work: run `teamctl --version`, `teamctl providers`, and
   `teamctl models`, and show me the output.

5. Report what you did, what you skipped and why, and finish by telling me
   my controls:
     - from the shell: `teamctl config --menu` to adjust preferences,
       `teamctl lead on|off|status` for the lead identity,
       `./uninstall.sh` (or `teamctl lead off` first) to undo everything.
     - from a chat: with lead mode on, I can just say "open the teamctl
       menu" to any lead agent and it will present and apply my settings.
```
