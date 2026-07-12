"""Tests for `teamctl lead` (manager identity tiers) and `teamctl config`.

Everything runs against a throwaway HOME — the real ~/.claude, ~/.config and
friends are never touched. No tmux needed.

Run with:  python3 -m unittest discover -s tests
"""

import contextlib
import importlib.util
import io
import json
import os
import tempfile
import tomllib
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEAMCTL = HERE.parent / "teamctl"

loader = SourceFileLoader("teamctl", str(TEAMCTL))
spec = importlib.util.spec_from_loader("teamctl", loader)
tc = importlib.util.module_from_spec(spec)
loader.exec_module(tc)


class ThrowawayHomeTestCase(unittest.TestCase):
    """HOME points at a fresh temp dir; scripted stdin via tc._input."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.home = Path(self.tmpdir.name)
        self._home_env = os.environ.get("HOME")
        os.environ["HOME"] = str(self.home)
        self._input = tc._input

    def tearDown(self):
        tc._input = self._input
        if self._home_env is not None:
            os.environ["HOME"] = self._home_env
        self.tmpdir.cleanup()

    def run_cli(self, argv, answers=()):
        """Run teamctl with scripted answers; running out of answers means
        'accept the default' (same as EOF on a real terminal)."""
        it = iter(answers)
        tc._input = lambda prompt: next(it)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = tc.main(argv)
        return rc, out.getvalue(), err.getvalue()

    @property
    def skill_md(self):
        return self.home / ".claude" / "skills" / "teamctl-lead" / "SKILL.md"

    @property
    def claude_md(self):
        return self.home / ".claude" / "CLAUDE.md"

    @property
    def settings(self):
        return self.home / ".claude" / "settings.json"

    @property
    def cfg(self):
        return self.home / ".config" / "agent-team" / "config.toml"


class LeadOnTests(ThrowawayHomeTestCase):
    def test_on_installs_skill_and_claude_md_block(self):
        rc, out, _ = self.run_cli(["lead", "on"], answers=["n"])  # decline hook
        self.assertEqual(rc, 0)
        text = self.skill_md.read_text()
        self.assertTrue(text.startswith("---\nname: teamctl-lead\n"))
        self.assertIn("description:", text.splitlines()[2])
        self.assertIn("teamctl shutdown", text)
        cm = self.claude_md.read_text()
        self.assertEqual(cm.count(tc.LEAD_MD_BEGIN), 1)
        self.assertEqual(cm.count(tc.LEAD_MD_END), 1)
        self.assertIn("teamctl usage", cm)
        # hook declined: settings.json must not even be created
        self.assertFalse(self.settings.exists())
        self.assertIn("Summary of changes", out)
        self.assertIn("Controls", out)                      # discoverability footer

    def test_on_twice_appends_block_once(self):
        self.assertEqual(self.run_cli(["lead", "on"])[0], 0)
        rc, out, _ = self.run_cli(["lead", "on"])
        self.assertEqual(rc, 0)
        self.assertEqual(self.claude_md.read_text().count(tc.LEAD_MD_BEGIN), 1)
        self.assertIn("skipping", out)

    def test_on_preserves_existing_claude_md_and_backs_up(self):
        self.claude_md.parent.mkdir(parents=True)
        self.claude_md.write_text("# my own rules\nalways be kind\n")
        rc, _, _ = self.run_cli(["lead", "on"])
        self.assertEqual(rc, 0)
        cm = self.claude_md.read_text()
        self.assertIn("# my own rules", cm)
        self.assertIn(tc.LEAD_MD_BEGIN, cm)
        bak = Path(str(self.claude_md) + ".bak-teamctl")
        self.assertTrue(bak.exists())
        self.assertNotIn(tc.LEAD_MD_BEGIN, bak.read_text())

    def test_on_updates_changed_skill_with_backup(self):
        self.assertEqual(self.run_cli(["lead", "on"])[0], 0)
        self.skill_md.write_text("stale contents")
        rc, out, _ = self.run_cli(["lead", "on"])
        self.assertEqual(rc, 0)
        self.assertEqual(self.skill_md.read_text(), tc.LEAD_SKILL_MD)
        bak = self.skill_md.with_name("SKILL.md.bak-teamctl")
        self.assertEqual(bak.read_text(), "stale contents")
        self.assertIn("updated", out)


class LeadOffTests(ThrowawayHomeTestCase):
    def test_off_removes_block_but_preserves_preexisting_content(self):
        self.claude_md.parent.mkdir(parents=True)
        self.claude_md.write_text("# my own rules\nalways be kind\n")
        self.assertEqual(self.run_cli(["lead", "on"])[0], 0)
        rc, out, _ = self.run_cli(["lead", "off"])
        self.assertEqual(rc, 0)
        cm = self.claude_md.read_text()
        self.assertIn("# my own rules", cm)
        self.assertIn("always be kind", cm)
        self.assertNotIn(tc.LEAD_MD_BEGIN, cm)
        self.assertNotIn("teamctl lead mode", cm)
        self.assertFalse(self.skill_md.parent.exists())
        self.assertTrue(Path(str(self.claude_md) + ".bak-teamctl-off").exists())
        self.assertIn("removed", out)

    def test_off_deletes_claude_md_it_created(self):
        self.assertEqual(self.run_cli(["lead", "on"])[0], 0)
        rc, _, _ = self.run_cli(["lead", "off"])
        self.assertEqual(rc, 0)
        # the file held only our block, so it is gone (backup kept)
        self.assertFalse(self.claude_md.exists())
        self.assertTrue(Path(str(self.claude_md) + ".bak-teamctl-off").exists())

    def test_off_tolerates_partial_and_empty_installs(self):
        # nothing installed at all
        rc, out, _ = self.run_cli(["lead", "off"])
        self.assertEqual(rc, 0)
        self.assertIn("nothing to remove", out)
        # partial: block installed but skill dir manually deleted
        self.assertEqual(self.run_cli(["lead", "on"])[0], 0)
        import shutil
        shutil.rmtree(self.skill_md.parent)
        rc, out, _ = self.run_cli(["lead", "off"])
        self.assertEqual(rc, 0)
        self.assertIn("left alone", out)
        self.assertFalse(self.claude_md.exists())

    def test_skill_backup_lands_outside_skills_dir(self):
        self.assertEqual(self.run_cli(["lead", "on"])[0], 0)
        self.assertEqual(self.run_cli(["lead", "off"])[0], 0)
        bak = self.home / ".claude" / "teamctl-lead-skill.bak-teamctl-off"
        self.assertTrue((bak / "SKILL.md").exists())
        self.assertFalse((self.home / ".claude" / "skills" / "teamctl-lead").exists())


class LeadHookTests(ThrowawayHomeTestCase):
    def _hook_entries(self):
        data = json.loads(self.settings.read_text())
        return data, (data.get("hooks") or {}).get("UserPromptSubmit") or []

    def test_hook_added_minimally_and_removed_cleanly(self):
        self.settings.parent.mkdir(parents=True)
        foreign = {"hooks": [{"type": "command", "command": "echo other-hook"}]}
        self.settings.write_text(json.dumps({
            "model": "opus",
            "hooks": {"UserPromptSubmit": [foreign]},
        }, indent=2))

        rc, _, _ = self.run_cli(["lead", "on", "--hook"])
        self.assertEqual(rc, 0)
        data, ups = self._hook_entries()
        self.assertEqual(data["model"], "opus")             # untouched
        self.assertEqual(len(ups), 2)                       # foreign + ours
        self.assertEqual(ups[0], foreign)
        self.assertIn("teamctl-lead", ups[1]["hooks"][0]["command"])
        self.assertEqual(ups[1]["hooks"][0]["type"], "command")
        self.assertTrue(Path(str(self.settings) + ".bak-teamctl").exists())

        # second run must not add a duplicate
        rc, out, _ = self.run_cli(["lead", "on", "--hook"])
        self.assertEqual(rc, 0)
        _, ups = self._hook_entries()
        self.assertEqual(len(ups), 2)
        self.assertIn("skipping", out)

        # off removes ours, keeps the foreign hook and other settings
        rc, _, _ = self.run_cli(["lead", "off"])
        self.assertEqual(rc, 0)
        data, ups = self._hook_entries()
        self.assertEqual(data["model"], "opus")
        self.assertEqual(ups, [foreign])
        self.assertTrue(Path(str(self.settings) + ".bak-teamctl-off").exists())

    def test_hook_removal_drops_empty_hooks_key(self):
        rc, _, _ = self.run_cli(["lead", "on", "--hook"])
        self.assertEqual(rc, 0)
        data, ups = self._hook_entries()
        self.assertEqual(len(ups), 1)
        rc, _, _ = self.run_cli(["lead", "off"])
        self.assertEqual(rc, 0)
        data = json.loads(self.settings.read_text())
        self.assertNotIn("hooks", data)                     # tidied away
        self.assertEqual(data, {})                          # nothing else added

    def test_hook_refuses_unparseable_settings(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text("{this is not json")
        rc, out, _ = self.run_cli(["lead", "on", "--hook"])
        self.assertEqual(rc, 0)                             # non-fatal, like init
        self.assertIn("could not parse", out)
        self.assertEqual(self.settings.read_text(), "{this is not json")
        # off must also leave it untouched
        rc, out, _ = self.run_cli(["lead", "off"])
        self.assertEqual(rc, 0)
        self.assertEqual(self.settings.read_text(), "{this is not json")
        self.assertIn("left untouched", out)

    def test_hook_prompt_defaults_to_yes(self):
        # an explicit "n" declines the recommended hook…
        rc, _, _ = self.run_cli(["lead", "on"], answers=["n"])
        self.assertEqual(rc, 0)
        self.assertFalse(self.settings.exists())
        # …but the default (unanswered prompt / EOF) installs it
        rc, _, _ = self.run_cli(["lead", "on"])
        self.assertEqual(rc, 0)
        _, ups = self._hook_entries()
        self.assertEqual(len(ups), 1)
        self.assertIn("teamctl-lead", ups[0]["hooks"][0]["command"])


class LeadStatusTests(ThrowawayHomeTestCase):
    def test_status_tracks_each_tier(self):
        rc, out, _ = self.run_cli(["lead", "status"])
        self.assertEqual(rc, 0)
        self.assertEqual(out.count("not installed"), 3)
        self.assertIn("Controls", out)                      # discoverability footer

        self.assertEqual(self.run_cli(["lead", "on"], answers=["n"])[0], 0)
        rc, out, _ = self.run_cli(["lead", "status"])
        self.assertEqual(rc, 0)
        st = tc._lead_status()
        self.assertEqual(st, {"skill": "installed",
                              "claude_md": "installed",
                              "hook": "not installed"})
        self.assertEqual(out.count("not installed"), 1)

        self.assertEqual(self.run_cli(["lead", "on", "--hook"])[0], 0)
        st = tc._lead_status()
        self.assertEqual(set(st.values()), {"installed"})

        self.assertEqual(self.run_cli(["lead", "off"])[0], 0)
        st = tc._lead_status()
        self.assertEqual(set(st.values()), {"not installed"})

    def test_status_reports_unparseable_settings(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text("nope[")
        self.assertIn("unknown", tc._lead_status()["hook"])


class InitLeadOfferTests(ThrowawayHomeTestCase):
    """The wizard's third offer: 'Install lead mode ...?' (default n)."""

    def setUp(self):
        super().setUp()
        self._which = tc.shutil.which
        self._auth = tc.AUTH_PATHS
        tc.shutil.which = lambda name, *a, **k: (
            "/fake/bin/claude" if name == "claude" else None)
        auth = self.home / "auth-claude"
        auth.write_text("x")
        tc.AUTH_PATHS = {"claude": auth,
                         "codex": self.home / "no-codex-auth",
                         "grok": self.home / "no-grok-auth"}

    def tearDown(self):
        tc.shutil.which = self._which
        tc.AUTH_PATHS = self._auth
        super().tearDown()

    def test_init_yes_skips_lead_mode(self):
        rc, _, _ = self.run_cli(["init", "--yes"])
        self.assertEqual(rc, 0)
        self.assertFalse(self.skill_md.exists())
        self.assertFalse(self.claude_md.exists())

    def test_init_default_answer_skips_lead_mode(self):
        # model, effort, verbosity, tmux n, statusline n, lead <default>
        rc, _, _ = self.run_cli(["init"], answers=["", "", "", "n", "n"])
        self.assertEqual(rc, 0)
        self.assertFalse(self.skill_md.exists())

    def test_init_yes_answer_installs_lead_mode(self):
        # ... lead y, hook n
        rc, out, _ = self.run_cli(
            ["init"], answers=["", "", "", "n", "n", "y", "n"])
        self.assertEqual(rc, 0)
        self.assertTrue(self.skill_md.exists())
        self.assertIn(tc.LEAD_MD_BEGIN, self.claude_md.read_text())
        self.assertFalse(self.settings.exists())            # hook declined
        self.assertIn("Summary of changes", out)


class ConfigShowSetTests(ThrowawayHomeTestCase):
    def _seed(self):
        self.cfg.parent.mkdir(parents=True, exist_ok=True)
        self.cfg.write_text(
            '[output]\nverbosity = "normal"\n\n'
            '[providers.claude]\nmodel = "opus"\neffort = "high"\n')

    def test_bare_config_without_file(self):
        rc, out, _ = self.run_cli(["config"])
        self.assertEqual(rc, 1)
        self.assertIn("no config", out)
        self.assertIn("teamctl init", out)

    def test_bare_config_pretty_prints_dotted_keys(self):
        self._seed()
        rc, out, _ = self.run_cli(["config"])
        self.assertEqual(rc, 0)
        self.assertIn('output.verbosity = "normal"', out)
        self.assertIn('providers.claude.model = "opus"', out)

    def test_set_preserves_other_keys_and_backs_up(self):
        self._seed()
        rc, out, _ = self.run_cli(["config", "providers.claude.model", "sonnet"])
        self.assertEqual(rc, 0)
        data = tomllib.loads(self.cfg.read_text())
        self.assertEqual(data["providers"]["claude"]["model"], "sonnet")
        self.assertEqual(data["providers"]["claude"]["effort"], "high")
        self.assertEqual(data["output"]["verbosity"], "normal")
        bak = self.cfg.with_name("config.toml.bak-teamctl")
        self.assertTrue(bak.exists())
        self.assertIn('model = "opus"', bak.read_text())
        self.assertIn("set providers.claude.model", out)

    def test_set_creates_file_and_new_tables(self):
        rc, _, _ = self.run_cli(["config", "providers.codex.effort", "xhigh"])
        self.assertEqual(rc, 0)
        data = tomllib.loads(self.cfg.read_text())
        self.assertEqual(data["providers"]["codex"]["effort"], "xhigh")

    def test_set_list_and_bool_values(self):
        rc, _, _ = self.run_cli(["config", "routing.preference", "grok, claude"])
        self.assertEqual(rc, 0)
        data = tomllib.loads(self.cfg.read_text())
        self.assertEqual(data["routing"]["preference"], ["grok", "claude"])
        # routing.preference stays a list even for a single entry
        rc, _, _ = self.run_cli(["config", "routing.preference", "claude"])
        self.assertEqual(rc, 0)
        data = tomllib.loads(self.cfg.read_text())
        self.assertEqual(data["routing"]["preference"], ["claude"])
        rc, _, _ = self.run_cli(["config", "output.fancy", "true"])
        self.assertEqual(rc, 0)
        data = tomllib.loads(self.cfg.read_text())
        self.assertIs(data["output"]["fancy"], True)

    def test_get_single_key(self):
        self._seed()
        rc, out, _ = self.run_cli(["config", "providers.claude.model"])
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), '"opus"')
        rc, _, err = self.run_cli(["config", "providers.claude.nope"])
        self.assertEqual(rc, 1)
        self.assertIn("not set", err)

    def test_set_refuses_overwriting_a_table(self):
        self._seed()
        rc, _, err = self.run_cli(["config", "providers.claude", "x"])
        self.assertNotEqual(rc, 0)
        self.assertIn("is a table", err)
        # file untouched
        self.assertEqual(
            tomllib.loads(self.cfg.read_text())["providers"]["claude"]["model"],
            "opus")

    def test_set_refuses_bad_toml(self):
        self.cfg.parent.mkdir(parents=True, exist_ok=True)
        self.cfg.write_text("not = toml [")
        rc, _, err = self.run_cli(["config", "output.verbosity", "terse"])
        self.assertNotEqual(rc, 0)
        self.assertIn("could not parse", err)
        self.assertEqual(self.cfg.read_text(), "not = toml [")

    def test_set_after_init_yes_preserves_provider_sections(self):
        _which, _auth = tc.shutil.which, tc.AUTH_PATHS
        tc.shutil.which = lambda name, *a, **k: (
            "/fake/bin/claude" if name == "claude" else None)
        auth = self.home / "auth-claude"
        auth.write_text("x")
        tc.AUTH_PATHS = {"claude": auth,
                         "codex": self.home / "no-codex-auth",
                         "grok": self.home / "no-grok-auth"}
        try:
            self.assertEqual(self.run_cli(["init", "--yes"])[0], 0)
            rc, _, _ = self.run_cli(["config", "output.verbosity", "terse"])
            self.assertEqual(rc, 0)
            text = self.cfg.read_text()
            self.assertIn("[providers.claude]", text)       # section survives
            data = tomllib.loads(text)
            self.assertEqual(data["output"]["verbosity"], "terse")
        finally:
            tc.shutil.which = _which
            tc.AUTH_PATHS = _auth


class ConfigMenuTests(ThrowawayHomeTestCase):
    def _seed(self):
        self.cfg.parent.mkdir(parents=True, exist_ok=True)
        self.cfg.write_text(
            '[output]\nverbosity = "normal"\n\n'
            '[providers.claude]\nmodel = "opus"\n')

    def test_menu_without_config(self):
        rc, out, _ = self.run_cli(["config", "--menu"])
        self.assertEqual(rc, 1)
        self.assertIn("no config", out)

    def test_menu_edits_one_setting(self):
        self._seed()
        # pick #2 (providers.claude.model), set sonnet, finish
        rc, out, _ = self.run_cli(["config", "--menu"],
                                  answers=["2", "sonnet", ""])
        self.assertEqual(rc, 0)
        data = tomllib.loads(self.cfg.read_text())
        self.assertEqual(data["providers"]["claude"]["model"], "sonnet")
        self.assertEqual(data["output"]["verbosity"], "normal")
        self.assertIn("wrote", out)
        self.assertTrue(self.cfg.with_name("config.toml.bak-teamctl").exists())

    def test_menu_rejects_bad_number_and_saves_nothing(self):
        self._seed()
        before = self.cfg.read_text()
        rc, out, _ = self.run_cli(["config", "--menu"], answers=["99", "0", ""])
        self.assertEqual(rc, 0)
        self.assertIn("no setting numbered '99'", out)
        self.assertIn("no setting numbered '0'", out)
        self.assertIn("nothing changed", out)
        self.assertEqual(self.cfg.read_text(), before)

    def test_menu_rejects_key_value_arguments(self):
        rc, _, err = self.run_cli(["config", "--menu", "output.verbosity"])
        self.assertEqual(rc, 2)
        self.assertIn("--menu", err)


if __name__ == "__main__":
    unittest.main()
