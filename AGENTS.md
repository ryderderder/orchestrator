# Agents: start here

This repo is **teamctl** — provider-agnostic AI agent teams on tmux.

- If you are an agent **using or operating** teamctl (installing it,
  acting as a team lead, driving teammates): read
  **[docs/AGENT_GUIDE.md](docs/AGENT_GUIDE.md)** — the machine-oriented
  contract (syntax, exit codes, states, `--json` surfaces, recovery
  recipes). [llms.txt](llms.txt) is the short index.
- If you are an agent **developing this repo**: run the tests before and
  after (`python3 -m unittest discover -s tests`, inside tmux for the live
  tier); never change state-file or handoff formats without reading
  AGENT_GUIDE §3; the core rule everywhere is *refuse, don't guess*.
