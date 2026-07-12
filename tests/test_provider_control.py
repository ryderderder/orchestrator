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


if __name__ == "__main__":
    unittest.main()
