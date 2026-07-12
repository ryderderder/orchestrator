"""v0.5.2 per-provider control: enable/disable, model pick, effort pick.

Disabled = excluded from routing and --provider defaults, refused when
named explicitly (with the exact re-enable command), still SHOWN in the
tables, config preserved. Model/effort choices offer only what each CLI
is known to accept (verified against the installed binaries 2026-07-12);
free text stays open everywhere — the provider CLI is the validator.

Run with:  python3 -m unittest tests.test_provider_control
"""

import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEAMCTL = HERE.parent / "teamctl"

loader = SourceFileLoader("teamctl_control", str(TEAMCTL))
spec = importlib.util.spec_from_loader("teamctl_control", loader)
tc = importlib.util.module_from_spec(spec)
loader.exec_module(tc)


class _ControlSandbox(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory(prefix="teamctl-ctl-")
        self.dir = Path(self.tmpdir.name)
        self._home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.dir)
        os.environ["TEAMCTL_STATE"] = str(self.dir / "state.json")
        self._saved_env = {}
        for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "XAI_API_KEY",
                    "GEMINI_API_KEY", "GOOGLE_API_KEY",
                    "GOOGLE_APPLICATION_CREDENTIALS"):
            self._saved_env[var] = os.environ.pop(var, None)
        os.environ["TEAMCTL_NO_KEYCHAIN"] = "1"
        self._which = tc.shutil.which
        self.installed = {"claude", "codex", "grok"}
        tc.shutil.which = lambda name, *a, **k: (
            f"/fake/bin/{name}" if name in self.installed else None)
        self._auth = tc.provider_auth_state
        tc.provider_auth_state = lambda p: ("signed-in", "")

    def tearDown(self):
        tc.shutil.which = self._which
        tc.provider_auth_state = self._auth
        os.environ.pop("TEAMCTL_NO_KEYCHAIN", None)
        for var, val in self._saved_env.items():
            if val is not None:
                os.environ[var] = val
        os.environ.pop("TEAMCTL_STATE", None)
        if self._home is not None:
            os.environ["HOME"] = self._home
        self.tmpdir.cleanup()

    def write_config(self, text: str) -> None:
        cfg = self.dir / ".config" / "agent-team"
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "config.toml").write_text(text)

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = tc.main(list(argv))
        return rc, out.getvalue(), err.getvalue()


class EnabledFlagTests(_ControlSandbox):
    def test_default_is_enabled(self):
        for p in ("claude", "codex", "grok", "gemini"):
            self.assertTrue(tc.provider_enabled(p), p)

    def test_config_disables(self):
        self.write_config("[providers.codex]\nenabled = false\n")
        self.assertFalse(tc.provider_enabled("codex"))
        self.assertTrue(tc.provider_enabled("claude"))
        # ...and the model/effort prefs beside it are preserved untouched
        self.write_config("[providers.codex]\nenabled = false\n"
                          'model = "gpt-5.5"\neffort = "high"\n')
        self.assertEqual(tc.provider_defaults("codex"),
                         ("gpt-5.5", "high"))

    def test_route_excludes_disabled_with_reason(self):
        self.write_config("[providers.claude]\nenabled = false\n")
        selected, _pref, exclusions, _rank = tc.route_select()
        self.assertNotEqual(selected, "claude")
        self.assertEqual(exclusions["claude"], "disabled")
        rc, out, _ = self.run_cli("route", "r", "--task", "t", "--dry-run")
        self.assertEqual(rc, 0)
        self.assertIn("claude: disabled", out)

    def test_explicit_provider_refused_with_reenable_command(self):
        self.write_config("[providers.codex]\nenabled = false\n")
        rc, _, err = self.run_cli("spawn", "r", "--provider", "codex",
                                  "--dry-run")
        self.assertEqual(rc, 2)
        self.assertIn("disabled", err)
        self.assertIn("teamctl config providers.codex.enabled true", err)

    def test_default_provider_skips_disabled_preference_head(self):
        self.write_config('[routing]\npreference = ["codex", "claude"]\n\n'
                          "[providers.codex]\nenabled = false\n")
        self.assertEqual(tc.default_provider(), "claude")

    def test_all_preferred_disabled_means_no_default(self):
        self.write_config('[routing]\npreference = ["codex"]\n\n'
                          "[providers.codex]\nenabled = false\n")
        self.assertIsNone(tc.default_provider())

    def test_available_providers_excludes_disabled(self):
        self.write_config("[providers.grok]\nenabled = false\n")
        self.assertNotIn("grok", tc.available_providers())

    def test_tables_still_show_disabled_honestly(self):
        self.write_config("[providers.grok]\nenabled = false\n")
        rc, out, _ = self.run_cli("providers")
        self.assertEqual(rc, 0)
        self.assertIn("grok", out)
        self.assertIn("disabled", out)
        self.assertIn("re-enable: teamctl config providers.grok.enabled "
                      "true", out)
        rc, out, _ = self.run_cli("providers", "--json")
        self.assertEqual(json.loads(out)["grok"]["state"], "disabled")
        rc, out, _ = self.run_cli("usage", "--json")
        self.assertEqual(json.loads(out)["states"]["grok"]["state"],
                         "disabled")

    def test_chat_provider_disabled_is_an_honest_error(self):
        self.write_config('[lead]\nchat_provider = "claude"\n\n'
                          "[providers.claude]\nenabled = false\n")
        prov, _m, _e, err = tc._resolve_chat()
        self.assertIsNone(prov)
        self.assertIn("disabled", err)
        self.assertIn("providers.claude.enabled true", err)

    def test_custom_provider_disable_uses_same_pref_table(self):
        # the custom BLOCK defines the provider; [providers.<name>] holds
        # its runtime prefs — enabled included
        self.write_config("""
[providers.custom.textctl]
command = "textctl"
headless_args = ["{task}"]

[providers.textctl]
enabled = false
""")
        self.assertIn("textctl", tc.routable_providers())
        self.assertFalse(tc.provider_enabled("textctl"))
        _sel, _p, exclusions, _r = tc.route_select(["textctl"])
        self.assertEqual(exclusions["textctl"], "disabled")

    def test_doctor_counts_disabled_out_of_usable(self):
        self.write_config("[providers.claude]\nenabled = false\n"
                          "[providers.codex]\nenabled = false\n"
                          "[providers.grok]\nenabled = false\n")
        status, detail = tc._check_providers()
        self.assertNotEqual(status, "ok")   # nothing usable remains


class ChoiceTests(_ControlSandbox):
    def test_claude_effort_choices_are_the_verified_five(self):
        self.assertEqual(tc._effort_choices_for("claude"),
                         ["low", "medium", "high", "xhigh", "max"])

    def test_gemini_and_shell_have_no_effort_choices(self):
        self.assertIsNone(tc._effort_choices_for("gemini"))
        self.assertIsNone(tc._effort_choices_for("shell"))

    def _codex_cache(self):
        d = self.dir / ".codex"
        d.mkdir(exist_ok=True)
        (d / "models_cache.json").write_text(json.dumps({
            "fetched_at": "2026-07-12", "models": [
                {"slug": "gpt-5.6-sol", "supported_reasoning_levels":
                 [{"effort": e} for e in
                  ("low", "medium", "high", "xhigh", "max", "ultra")]},
                {"slug": "gpt-5.4", "supported_reasoning_levels":
                 [{"effort": e} for e in
                  ("low", "medium", "high", "xhigh")]},
            ]}))

    def test_codex_effort_choices_follow_the_model(self):
        self._codex_cache()
        self.assertEqual(
            tc._effort_choices_for("codex", "gpt-5.4"),
            ["low", "medium", "high", "xhigh"])
        self.assertIn("ultra",
                      tc._effort_choices_for("codex", "gpt-5.6-sol"))
        # unknown model -> the union across the cache
        self.assertIn("ultra", tc._effort_choices_for("codex", "nope"))

    def test_codex_effort_without_cache_degrades_to_suggestions(self):
        self.assertEqual(tc._effort_choices_for("codex"),
                         list(tc.EFFORT_CHOICES))

    def test_model_menu_choices_come_from_discovery(self):
        # claude: documented aliases, '' (CLI default) first
        choices = tc._menu_choices("providers.claude.model", "")
        self.assertEqual(choices[0], "")
        for alias in tc.CLAUDE_MODEL_ALIASES:
            self.assertIn(alias, choices)
        # gemini: no discovery -> free text (None)
        self.assertIsNone(tc._menu_choices("providers.gemini.model", ""))
        # codex with a cache -> slugs
        self._codex_cache()
        choices = tc._menu_choices("providers.codex.model", "")
        self.assertIn("gpt-5.6-sol", choices)

    def test_effort_menu_choices_are_per_provider(self):
        self.assertIn("max", tc._menu_choices("providers.claude.effort",
                                              ""))
        self._codex_cache()
        self.write_config('[providers.codex]\nmodel = "gpt-5.4"\n')
        self.assertNotIn("ultra", tc._menu_choices(
            "providers.codex.effort", ""))


class CatalogTests(_ControlSandbox):
    def _rows(self, cfg_text=""):
        if cfg_text:
            self.write_config(cfg_text)
        data = {}
        p = self.dir / ".config" / "agent-team" / "config.toml"
        if p.exists():
            import tomllib
            data = tomllib.loads(p.read_text())
        return tc.settings_catalog(data)

    def test_every_routable_provider_gets_control_rows(self):
        rows = self._rows()
        by_key = {r["key"]: r for r in rows}
        for prov in ("claude", "codex", "grok", "gemini"):
            self.assertIn(f"providers.{prov}.enabled", by_key, prov)
            self.assertIn(f"providers.{prov}.model", by_key, prov)
        # enabled defaults True and cycles as a bool
        row = by_key["providers.claude.enabled"]
        self.assertIs(row["value"], True)
        self.assertEqual(row["choices"], [True, False])
        # effort rows only where the CLI has effort control
        self.assertIn("providers.claude.effort", by_key)
        self.assertNotIn("providers.gemini.effort", by_key)

    def test_configured_disabled_state_shows_in_catalog(self):
        rows = self._rows("[providers.codex]\nenabled = false\n")
        row = next(r for r in rows
                   if r["key"] == "providers.codex.enabled")
        self.assertIs(row["value"], False)

    def test_custom_provider_rows_present_with_free_text_model(self):
        rows = self._rows("""
[providers.custom.textctl]
command = "textctl"
headless_args = ["{task}"]
""")
        by_key = {r["key"]: r for r in rows}
        self.assertIn("providers.textctl.enabled", by_key)
        self.assertIsNone(by_key["providers.textctl.model"]["choices"])
        self.assertNotIn("providers.textctl.effort", by_key)  # no effort_args

    def test_config_cli_round_trip_bool(self):
        rc, out, _ = self.run_cli("config", "providers.codex.enabled",
                                  "false")
        self.assertEqual(rc, 0)
        self.assertFalse(tc.provider_enabled("codex"))
        rc, out, _ = self.run_cli("config", "providers.codex.enabled",
                                  "true")
        self.assertEqual(rc, 0)
        self.assertTrue(tc.provider_enabled("codex"))


class StripEnvTests(_ControlSandbox):
    """v0.5.3 strip_env: env vars removed from the TEAMMATE's process
    only (an `env -u` prefix on the command teamctl composes — no tmux
    environment surgery, nothing else's env changes). Motivating case:
    agy refuses keychain auth whenever an inherited SSH_CONNECTION is
    present, and a tmux session created over SSH carries that marker for
    its whole lifetime."""

    STRIP_BLOCK = """
[providers.custom.sshy]
command = "sshy"
headless_args = ["-p", "{task}"]
interactive_args = ["--chat"]
strip_env = ["SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY"]
"""

    def test_schema_parses_and_validates_names(self):
        self.write_config(self.STRIP_BLOCK)
        spec = tc.provider_spec("sshy")
        self.assertEqual(spec["strip_env"],
                         ["SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY"])
        self.assertEqual(tc._strip_env_argv("sshy"),
                         ["env", "-u", "SSH_CONNECTION", "-u", "SSH_CLIENT",
                          "-u", "SSH_TTY"])
        # built-ins don't strip anything
        for p in ("claude", "codex", "grok", "gemini", "shell"):
            self.assertEqual(tc._strip_env_argv(p), [], p)

    def test_bad_variable_names_are_dropped_with_a_warning(self):
        self.write_config("""
[providers.custom.badvars]
command = "badvars"
headless_args = ["{task}"]
strip_env = ["GOOD_ONE", "bad-dash", "1LEADING", "in valid"]
""")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            spec = tc.provider_spec("badvars")
        self.assertEqual(spec["strip_env"], ["GOOD_ONE"])
        self.assertIn("not a valid variable name", err.getvalue())

    def test_interactive_launch_line_gets_the_prefix(self):
        self.write_config(self.STRIP_BLOCK)
        line = tc.build_launch_line("sshy", "hello", "/tmp")
        self.assertIn("exec env -u SSH_CONNECTION -u SSH_CLIENT "
                      "-u SSH_TTY sshy --chat hello", line)
        # ...and a provider without strip_env is untouched
        self.assertNotIn("env -u",
                         tc.build_launch_line("claude", "hi", "/tmp"))

    def test_dispatch_wrapper_prefixes_the_provider_only(self):
        self.write_config(self.STRIP_BLOCK)
        captured = {}
        saved_open, saved_load = tc._open_pane, tc.load_state
        tc._open_pane = (lambda cmd, existing:
                         captured.setdefault("cmd", cmd) or "%x")
        tc.load_state = lambda: {"teammates": {}}
        try:
            tc._dispatch_pane("r", self.dir / "hd",
                              ["sshy", "-p", "task"], str(self.dir),
                              "sshy", "")
        finally:
            tc._open_pane, tc.load_state = saved_open, saved_load
        self.assertIn("env -u SSH_CONNECTION -u SSH_CLIENT -u SSH_TTY "
                      "sshy -p task", captured["cmd"])
        # the wrapper machinery itself (pid/status bookkeeping) still runs
        # OUTSIDE the stripped env — the prefix wraps only the provider
        self.assertIn("echo $$ >", captured["cmd"])


@unittest.skipUnless(os.environ.get("TMUX"), "requires a live tmux session")
class LiveStripEnvTests(unittest.TestCase):
    """End-to-end proof in a real pane: a canary variable planted in the
    tmux session environment reaches an unstripped teammate and does NOT
    reach a stripped one."""

    def setUp(self):
        self.statedir = tempfile.TemporaryDirectory(prefix="teamctl-se-")
        self.dir = Path(self.statedir.name)
        os.environ["TEAMCTL_STATE"] = str(self.dir / "state.json")
        self._home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.dir)
        cfg = self.dir / ".config" / "agent-team"
        cfg.mkdir(parents=True)
        # two sh-backed custom providers: one strips the canary, one not
        (cfg / "config.toml").write_text("""
[providers.custom.stripped]
command = "sh"
headless_args = ["-c", "{task}"]
strip_env = ["TEAMCTL_CANARY"]

[providers.custom.plain]
command = "sh"
headless_args = ["-c", "{task}"]
""")
        self._wt = tc.worktree_settings
        tc.worktree_settings = lambda: {"enabled": False, "dir": "",
                                        "branch_prefix": "teamctl/",
                                        "cleanup": "auto"}
        out = tc.tmux("new-window", "-d", "-n", f"teamctl-se-{os.getpid()}",
                      "-P", "-F", "#{window_id} #{pane_id}").stdout.split()
        self.window_id, self.lead_pane = out[0], out[1]
        self._tmux_pane = os.environ.get("TMUX_PANE")
        os.environ["TMUX_PANE"] = self.lead_pane
        # plant the canary in the SESSION env: new panes inherit it
        tc.tmux("set-environment", "TEAMCTL_CANARY", "present")

    def tearDown(self):
        tc.tmux("set-environment", "-u", "TEAMCTL_CANARY", check=False)
        for role in list(tc.load_state()["teammates"]):
            tc.main(["shutdown", role])
        tc.tmux("kill-window", "-t", self.window_id, check=False)
        tc.worktree_settings = self._wt
        if self._tmux_pane is None:
            os.environ.pop("TMUX_PANE", None)
        else:
            os.environ["TMUX_PANE"] = self._tmux_pane
        if self._home is not None:
            os.environ["HOME"] = self._home
        os.environ.pop("TEAMCTL_STATE", None)
        self.statedir.cleanup()

    def _run_task(self, role, provider):
        rc = tc.main(["dispatch", role, "--provider", provider, "--task",
                      'echo "CANARY=${TEAMCTL_CANARY:-GONE}"',
                      "--cwd", str(self.dir)])
        self.assertEqual(rc, 0)
        import time as _t
        hd = Path(tc.load_state()["teammates"][role]["handoff"])
        deadline = _t.monotonic() + 20
        while _t.monotonic() < deadline and not (hd / "status").exists():
            _t.sleep(0.3)
        return (hd / "result.json").read_text()

    def test_canary_stripped_for_the_configured_provider_only(self):
        # control first: the canary genuinely reaches an unstripped pane
        self.assertIn("CANARY=present", self._run_task("ctl", "plain"))
        # the stripped provider never sees it
        self.assertIn("CANARY=GONE", self._run_task("exp", "stripped"))


if __name__ == "__main__":
    unittest.main()
