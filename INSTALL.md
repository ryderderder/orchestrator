# Installing Orchestrator — instructions for your AI agent

You are an agent installing Orchestrator for your user. Orchestrator runs AI
teammates — Claude Code / Codex / Grok / Gemini / Antigravity `agy` — as
labeled tmux panes, with quota-aware routing across the user's own
subscriptions. Follow these steps in order.

1. **Install** (the flag matters: `--no-init` stops the installer from
   entering tmux and taking over the terminal you are operating in):

       curl -fsSL https://raw.githubusercontent.com/ryderderder/orchestrator/main/install.sh | bash -s -- --no-init

   Rules while installing:
   - Ask the user before anything that needs sudo.
   - Never install a provider CLI without asking — the installer prints
     each one's official one-liner; show them and ask.
   - Make sure `~/.local/bin` is on the user's PATH; change their shell
     profile only with consent, and say exactly what you changed.

2. **Configure**: run `orchestrator init` (express — zero questions) and show
   the user its summary frame. Never pick a routing order for them.

3. **Offer lead mode**: `orchestrator lead on` installs a manager identity
   into every detected agent CLI (reversible: `orchestrator lead off`).
   Install it only on a yes.

4. **Verify**: run `orchestrator doctor` and show the output
   (exit 0 ok · 1 warn · 2 fail). `orchestrator providers` shows what is
   signed in.

5. **Orient yourself to operate it**: read `docs/AGENT_GUIDE.md` (the
   machine contract — command syntax, exit codes, states, `--json`
   surfaces, recovery recipes) and `llms.txt` from the repo, fetched the
   same way as this file.

6. **Report** what you did, what you skipped and why, and the user's
   controls: `orchestrator settings` (preferences cockpit) ·
   `orchestrator lead on|off|status` (manager identity) ·
   `orchestrator uninstall` (run `orchestrator lead off` first — the uninstaller
   removes the binary that reverses lead mode).
