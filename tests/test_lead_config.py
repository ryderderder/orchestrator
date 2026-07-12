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


def seed_signin(home: Path, *providers: str) -> None:
    """Write a provider's real signed-in artifact into a fixture HOME —
    the exact shapes the auth probes were verified against on a live
    signed-in install of each CLI."""
    for p in providers:
        if p == "claude":
            (home / ".claude.json").write_text(json.dumps(
                {"oauthAccount": {"emailAddress": "t@example.com"}}))
        elif p == "codex":
            (home / ".codex").mkdir(exist_ok=True)
            (home / ".codex" / "auth.json").write_text(json.dumps(
                {"auth_mode": "chatgpt", "OPENAI_API_KEY": None,
                 "tokens": {"access_token": "t"}, "last_refresh": "now"}))
        elif p == "grok":
            (home / ".grok").mkdir(exist_ok=True)
            (home / ".grok" / "auth.json").write_text(json.dumps(
                {"https://auth.x.ai::u1": {"key": "k",
                                           "refresh_token": "r"}}))


class ThrowawayHomeTestCase(unittest.TestCase):
    """HOME points at a fresh temp dir; scripted stdin via tc._input."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.home = Path(self.tmpdir.name)
        self._home_env = os.environ.get("HOME")
        os.environ["HOME"] = str(self.home)
        self._input = tc._input
        # keep the real machine's auth out of the sandbox: the keychain
        # probe reads the *user's* keychain regardless of HOME, and an
        # exported provider API key counts as signed in
        os.environ["TEAMCTL_NO_KEYCHAIN"] = "1"
        self._saved_env = {}
        for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "XAI_API_KEY"):
            self._saved_env[var] = os.environ.pop(var, None)
        # pin CLI detection: all three "installed", regardless of the machine
        # (lead's default --cli set and provider detection read shutil.which)
        self._which = tc.shutil.which
        tc.shutil.which = lambda name, *a, **k: (
            f"/fake/bin/{name}" if name in ("claude", "codex", "grok")
            else self._which(name))

    def tearDown(self):
        tc.shutil.which = self._which
        tc._input = self._input
        os.environ.pop("TEAMCTL_NO_KEYCHAIN", None)
        for var, val in self._saved_env.items():
            if val is not None:
                os.environ[var] = val
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

    def test_on_refreshes_stale_block_in_place(self):
        self.claude_md.parent.mkdir(parents=True)
        stale = tc.LEAD_MD_BEGIN + "\nOLD RULES from v0.1\n" + tc.LEAD_MD_END + "\n"
        self.claude_md.write_text("# before\n" + stale + "# after\n")
        rc, out, _ = self.run_cli(["lead", "on"], answers=["n"])
        self.assertEqual(rc, 0)
        text = self.claude_md.read_text()
        self.assertEqual(text.count(tc.LEAD_MD_BEGIN), 1)
        self.assertNotIn("OLD RULES", text)
        self.assertIn("teamctl usage", text)             # fresh block content
        # refreshed IN PLACE: still between the surrounding content
        self.assertLess(text.index("# before"), text.index(tc.LEAD_MD_BEGIN))
        self.assertLess(text.index(tc.LEAD_MD_END), text.index("# after"))
        self.assertIn("updated the teamctl-lead block", out)
        bak = Path(str(self.claude_md) + ".bak-teamctl")
        self.assertIn("OLD RULES", bak.read_text())
        # an up-to-date block is left alone
        rc, out, _ = self.run_cli(["lead", "on"], answers=["n"])
        self.assertEqual(rc, 0)
        self.assertIn("skipping", out)
        self.assertEqual(self.claude_md.read_text(), text)

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


class UninstallTests(ThrowawayHomeTestCase):
    """`teamctl uninstall` reverses install.sh + init, backups first,
    leaving config/state and lead mode alone (all against a throwaway
    HOME; no real files touched)."""

    def setUp(self):
        super().setUp()
        os.environ["TEAMCTL_STATE"] = str(
            self.home / ".local" / "state" / "agent-team" / "state.json")

    def tearDown(self):
        os.environ.pop("TEAMCTL_STATE", None)
        super().tearDown()

    def _seed_install(self, statusline_cmd="~/.local/bin/teamctl statusline"):
        bin_dir = self.home / ".local" / "bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "teamctl").write_text("#!/usr/bin/env python3\n")
        state = self.home / ".local" / "state" / "agent-team"
        state.mkdir(parents=True, exist_ok=True)
        (state / "install-meta.json").write_text(json.dumps(
            {"source": "curl", "bin_dir": str(bin_dir)}))
        tmux = self.home / ".tmux.conf"
        tmux.write_text("set -g mouse on\n\n" + tc.TMUX_BLOCK)
        settings = self.home / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps(
            {"model": "opus",
             "statusLine": {"type": "command", "command": statusline_cmd}}))
        return bin_dir, tmux, settings

    def test_uninstall_reverses_install_and_keeps_user_content(self):
        bin_dir, tmux, settings = self._seed_install()
        rc, out, _ = self.run_cli(["uninstall", "--yes"])
        self.assertEqual(rc, 0)
        self.assertFalse((bin_dir / "teamctl").exists())
        # tmux block gone, the user's own line preserved
        text = tmux.read_text()
        self.assertNotIn(tc.TMUX_MARKER_BEGIN, text)
        self.assertIn("set -g mouse on", text)
        # statusLine key removed, other settings kept
        data = json.loads(settings.read_text())
        self.assertNotIn("statusLine", data)
        self.assertEqual(data["model"], "opus")
        # metadata cleared; per-user data pointer printed
        self.assertFalse(
            (self.home / ".local" / "state" / "agent-team"
             / "install-meta.json").exists())
        self.assertIn("rm -rf ~/.config/agent-team", out)
        self.assertIn("teamctl lead off", out)

    def test_uninstall_removes_legacy_statusline_wiring_too(self):
        bin_dir, _tmux, settings = self._seed_install(
            statusline_cmd="~/.local/bin/claude-statusline")
        (bin_dir / "claude-statusline").write_text("# legacy\n")
        rc, _, _ = self.run_cli(["uninstall", "--yes"])
        self.assertEqual(rc, 0)
        self.assertFalse((bin_dir / "claude-statusline").exists())
        self.assertNotIn("statusLine", json.loads(settings.read_text()))

    def test_uninstall_leaves_foreign_statusline_alone(self):
        bin_dir, _tmux, settings = self._seed_install(
            statusline_cmd="/opt/other/statusline")
        rc, out, _ = self.run_cli(["uninstall", "--yes"])
        self.assertEqual(rc, 0)
        self.assertIn("statusLine",
                      json.loads(settings.read_text()))     # not ours: kept
        self.assertIn("not teamctl's", out)

    def test_uninstall_declined_without_yes(self):
        bin_dir, _t, _s = self._seed_install()
        rc, out, _ = self.run_cli(["uninstall"], answers=["n"])
        self.assertEqual(rc, 0)
        self.assertIn("nothing removed", out)
        self.assertTrue((bin_dir / "teamctl").exists())


class SettingsModelTests(ThrowawayHomeTestCase):
    """The `teamctl settings` MODEL layer (catalog / cycle / plain degrade)
    is pure and headless — the curses view is tested live elsewhere."""

    def _write_cfg(self, text):
        self.cfg.parent.mkdir(parents=True, exist_ok=True)
        self.cfg.write_text(text)

    def test_catalog_shows_effective_defaults_when_unset(self):
        # empty config -> every fixed key present at its documented default
        cat = {r["key"]: r for r in tc.settings_catalog({})}
        self.assertEqual(cat["update.mode"]["value"], "prompt")
        self.assertEqual(cat["update.check"]["value"], True)
        self.assertEqual(cat["lead.delegation"]["value"], "ask")
        self.assertEqual(cat["layout.lead_width"]["value"], 50)
        self.assertEqual(cat["output.verbosity"]["value"], "normal")

    def test_catalog_reflects_configured_values_and_providers(self):
        data = {"update": {"mode": "auto"},
                "providers": {"codex": {"model": "gpt-5.6", "effort": "xhigh"},
                              "claude": {"effort": "high"}}}
        cat = {r["key"]: r for r in tc.settings_catalog(data)}
        self.assertEqual(cat["update.mode"]["value"], "auto")
        self.assertEqual(cat["providers.codex.model"]["value"], "gpt-5.6")
        self.assertEqual(cat["providers.codex.effort"]["value"], "xhigh")
        # a provider with no model key defaults to '' (the CLI's own default)
        self.assertEqual(cat["providers.claude.model"]["value"], "")

    def test_enum_and_bool_rows_are_cycleable_free_rows_are_not(self):
        cat = {r["key"]: r for r in tc.settings_catalog({})}
        self.assertEqual(cat["update.mode"]["choices"],
                         ["prompt", "auto", "off"])
        self.assertEqual(cat["update.check"]["choices"], [True, False])
        self.assertIsNone(cat["lead.chat_model"]["choices"])   # free text

    def test_cycle_wraps_and_respects_direction(self):
        row = {"value": "prompt", "choices": ["prompt", "auto", "off"]}
        self.assertEqual(tc._settings_cycle(row, 1), "auto")
        row["value"] = "off"
        self.assertEqual(tc._settings_cycle(row, 1), "prompt")   # wraps
        self.assertEqual(tc._settings_cycle(row, -1), "auto")
        # an unknown current value lands on a valid choice, never raises
        self.assertIn(tc._settings_cycle(
            {"value": "weird", "choices": ["a", "b"]}, 1), ["a", "b"])

    def test_plain_degrade_prints_values_and_config_oneliners(self):
        self._write_cfg('[update]\nmode = "auto"\n')
        rc, out, _ = self.run_cli(["settings"])       # no TTY -> plain path
        self.assertEqual(rc, 0)
        self.assertIn("current settings", out)
        self.assertIn("update mode", out)
        self.assertIn("teamctl config update.mode auto", out)
        # bools render as lowercase true/false in the one-liner
        self.assertIn("teamctl config update.check true", out)
        # sections present
        self.assertIn("[default chat]", out)
        self.assertIn("[updates]", out)

    def test_settings_without_config_still_works(self):
        rc, out, _ = self.run_cli(["settings"])
        self.assertEqual(rc, 0)
        self.assertIn("no config yet", out)
        self.assertIn("teamctl config update.mode prompt", out)   # defaults


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
        # skill + three CLI blocks + hook
        self.assertEqual(out.count("not installed"), 5)
        self.assertIn("Controls", out)                      # discoverability footer

        self.assertEqual(self.run_cli(["lead", "on"], answers=["n"])[0], 0)
        rc, out, _ = self.run_cli(["lead", "status"])
        self.assertEqual(rc, 0)
        st = tc._lead_status()
        self.assertEqual(st, {"skill": "installed",
                              "blocks": {"claude": "installed",
                                         "codex": "installed",
                                         "grok": "installed"},
                              "hook": "not installed"})
        self.assertEqual(out.count("not installed"), 1)

        self.assertEqual(self.run_cli(["lead", "on", "--hook"])[0], 0)
        st = tc._lead_status()
        self.assertEqual(st["hook"], "installed")
        self.assertEqual(st["skill"], "installed")
        self.assertEqual(set(st["blocks"].values()), {"installed"})

        self.assertEqual(self.run_cli(["lead", "off"])[0], 0)
        st = tc._lead_status()
        self.assertEqual(st["hook"], "not installed")
        self.assertEqual(st["skill"], "not installed")
        self.assertEqual(set(st["blocks"].values()), {"not installed"})

    def test_status_reports_unparseable_settings(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text("nope[")
        self.assertIn("unknown", tc._lead_status()["hook"])


class InitLeadOfferTests(ThrowawayHomeTestCase):
    """The wizard's third offer: 'Install lead mode ...?' (default n)."""

    def setUp(self):
        super().setUp()
        self._offer_which = tc.shutil.which
        tc.shutil.which = lambda name, *a, **k: (
            "/fake/bin/claude" if name == "claude" else None)
        seed_signin(self.home, "claude")

    def tearDown(self):
        tc.shutil.which = self._offer_which
        super().tearDown()

    def test_init_yes_skips_lead_mode(self):
        rc, _, _ = self.run_cli(["init", "--yes"])
        self.assertEqual(rc, 0)
        self.assertFalse(self.skill_md.exists())
        self.assertFalse(self.claude_md.exists())

    def test_init_plain_path_never_offers_lead_mode(self):
        # spec §5: no integration prompts on the default plain path — the
        # trailing y answers must never reach a lead-mode offer
        rc, _, _ = self.run_cli(["init", "--custom"],
                                answers=["", "", "", "", "y", "y", "y"])
        self.assertEqual(rc, 0)
        self.assertFalse(self.skill_md.exists())

    def test_init_extras_escape_installs_lead_mode(self):
        # TEAMCTL_INIT_EXTRAS=1 re-enables the offers: model, effort, voice,
        # lead, write, tmux n, statusline n, lead-mode y, hook n
        os.environ["TEAMCTL_INIT_EXTRAS"] = "1"
        try:
            rc, out, _ = self.run_cli(
                ["init", "--custom"],
                answers=["", "", "", "", "y", "n", "n", "y", "n"])
        finally:
            os.environ.pop("TEAMCTL_INIT_EXTRAS", None)
        self.assertEqual(rc, 0)
        self.assertTrue(self.skill_md.exists())
        self.assertIn(tc.LEAD_MD_BEGIN, self.claude_md.read_text())
        self.assertFalse(self.settings.exists())            # hook declined


class LeadMultiCliTests(ThrowawayHomeTestCase):
    """lead --cli: blocks for codex (~/.codex/AGENTS.md) and grok
    (~/.grok/AGENTS.md) — both documented global-instructions paths."""

    def test_on_installs_blocks_for_all_detected_clis(self):
        rc, _, _ = self.run_cli(["lead", "on"], answers=["n"])
        self.assertEqual(rc, 0)
        for d, name in ((".claude", "CLAUDE.md"), (".codex", "AGENTS.md"),
                        (".grok", "AGENTS.md")):
            text = (self.home / d / name).read_text()
            self.assertEqual(text.count(tc.LEAD_MD_BEGIN), 1, f"{d}/{name}")

    def test_cli_flag_limits_scope_and_notes_claude_only_tiers(self):
        # pre-existing codex instructions must survive
        (self.home / ".codex").mkdir()
        (self.home / ".codex" / "AGENTS.md").write_text("# my codex rules\n")
        rc, out, _ = self.run_cli(["lead", "on", "--cli", "codex"])
        self.assertEqual(rc, 0)
        codex_md = (self.home / ".codex" / "AGENTS.md").read_text()
        self.assertIn("# my codex rules", codex_md)
        self.assertIn(tc.LEAD_MD_BEGIN, codex_md)
        self.assertFalse(self.claude_md.exists())
        self.assertFalse(self.skill_md.exists())        # skill is Claude-only
        self.assertFalse(self.settings.exists())        # hook is Claude-only
        self.assertIn("Claude Code mechanisms", out)
        # off --cli grok must not touch the codex block
        (self.home / ".grok").mkdir()
        (self.home / ".grok" / "AGENTS.md").write_text(tc.LEAD_CLAUDE_BLOCK)
        rc, _, _ = self.run_cli(["lead", "off", "--cli", "grok"])
        self.assertEqual(rc, 0)
        self.assertFalse((self.home / ".grok" / "AGENTS.md").exists())
        self.assertIn(tc.LEAD_MD_BEGIN,
                      (self.home / ".codex" / "AGENTS.md").read_text())

    def test_off_default_cleans_every_cli(self):
        self.assertEqual(self.run_cli(["lead", "on"], answers=["y"])[0], 0)
        rc, _, _ = self.run_cli(["lead", "off"])
        self.assertEqual(rc, 0)
        for d, name in ((".claude", "CLAUDE.md"), (".codex", "AGENTS.md"),
                        (".grok", "AGENTS.md")):
            self.assertFalse((self.home / d / name).exists())
        self.assertFalse(self.skill_md.parent.exists())
        self.assertEqual(json.loads(self.settings.read_text()), {})


class DefaultProviderTests(ThrowawayHomeTestCase):
    """--provider is never silently defaulted among several providers."""

    def _auth_up(self, *provs):
        seed_signin(self.home, *provs)

    def test_config_preference_first_entry_wins(self):
        self._auth_up("claude", "codex", "grok")
        self.cfg.parent.mkdir(parents=True)
        self.cfg.write_text('[routing]\npreference = ["grok", "codex"]\n')
        rc, out, _ = self.run_cli(["spawn", "r", "--dry-run"])
        self.assertEqual(rc, 0)
        self.assertIn("exec grok", out)

    def test_single_available_provider_is_the_default(self):
        self._auth_up("codex")
        rc, out, _ = self.run_cli(["spawn", "r", "--dry-run"])
        self.assertEqual(rc, 0)
        self.assertIn("exec codex", out)

    def test_multiple_available_means_no_silent_default(self):
        self._auth_up("claude", "grok")
        rc, _, err = self.run_cli(["spawn", "r", "--dry-run"])
        self.assertEqual(rc, 2)
        self.assertIn("detected: claude, grok", err)
        self.assertIn("routing.preference", err)
        rc, _, err = self.run_cli(["dispatch", "r", "--task", "t"])
        self.assertEqual(rc, 2)
        self.assertIn("no --provider given", err)

    def test_none_available_says_so(self):
        rc, _, err = self.run_cli(["spawn", "r", "--dry-run"])
        self.assertEqual(rc, 2)
        self.assertIn("detected: none", err)

    def test_bogus_preference_entry_is_reported(self):
        self._auth_up("claude", "codex")
        self.cfg.parent.mkdir(parents=True)
        self.cfg.write_text('[routing]\npreference = ["bogus"]\n')
        rc, _, err = self.run_cli(["spawn", "r", "--dry-run"])
        self.assertEqual(rc, 2)
        self.assertIn("unknown provider", err)


class GrokAuthHeuristicTests(ThrowawayHomeTestCase):
    """grok login detection: auth.json (observed artifact, holding at least
    one credential entry) first; signs of real CLI use as last resort;
    NEVER bare ~/.grok existence — `lead on` creates that directory on
    machines that never logged in."""

    def setUp(self):
        super().setUp()
        os.environ["TEAMCTL_STATE"] = str(self.home / "state.json")

    def tearDown(self):
        os.environ.pop("TEAMCTL_STATE", None)
        super().tearDown()

    def test_auth_json_is_the_primary_signal(self):
        seed_signin(self.home, "grok")
        self.assertTrue(tc.provider_authed("grok"))

    def test_empty_auth_json_is_not_login(self):
        # a credential-less {} (e.g. after a logout) must not read as a
        # login — v0.4.0 validates content, not bare file existence
        (self.home / ".grok").mkdir()
        (self.home / ".grok" / "auth.json").write_text("{}")
        self.assertFalse(tc.provider_authed("grok"))

    def test_lead_on_created_dir_is_not_login(self):
        # exactly what `teamctl lead on --cli grok` leaves behind
        (self.home / ".grok").mkdir()
        (self.home / ".grok" / "AGENTS.md").write_text(tc.LEAD_CLAUDE_BLOCK)
        self.assertFalse(tc.provider_authed("grok"))
        self.assertFalse((self.home / ".grok" / "auth.json").exists())

    def test_cli_use_markers_are_the_last_resort_with_caveat(self):
        (self.home / ".grok").mkdir()
        (self.home / ".grok" / "sessions").mkdir()          # real CLI data
        self.assertTrue(tc.provider_authed("grok"))
        rc, out, _ = self.run_cli(["providers"])
        self.assertEqual(rc, 0)
        self.assertIn("inferred from ~/.grok CLI data", out)

    def test_no_dir_means_not_authed(self):
        self.assertFalse(tc.provider_authed("grok"))


class InitRoutingOrderTests(ThrowawayHomeTestCase):
    """The wizard asks the USER for the auto-routing order."""

    def setUp(self):
        super().setUp()
        seed_signin(self.home, "claude", "codex")   # grok stays locked out

    def _config(self):
        return tomllib.loads(self.cfg.read_text())

    def test_wizard_writes_users_order(self):
        # plain path: claude model, codex model, effort, voice, lead,
        # ROUTE, write
        rc, _, _ = self.run_cli(
            ["init", "--custom"],
            answers=["", "", "", "", "", "codex, claude", "y"])
        self.assertEqual(rc, 0)
        self.assertEqual(self._config()["routing"]["preference"],
                         ["codex", "claude"])

    def test_wizard_drops_unknown_entries(self):
        # spec §6.3: unknowns dropped silently
        rc, _, _ = self.run_cli(
            ["init", "--custom"],
            answers=["", "", "", "", "", "gpt, codex", "y"])
        self.assertEqual(rc, 0)
        self.assertEqual(self._config()["routing"]["preference"], ["codex"])

    def test_blank_order_falls_back_to_documented_alphabetical(self):
        rc, _, _ = self.run_cli(
            ["init", "--custom"], answers=["", "", "", "", "", "", "y"])
        self.assertEqual(rc, 0)
        self.assertEqual(self._config()["routing"]["preference"],
                         ["claude", "codex"])

    def test_yes_writes_alphabetical_preference(self):
        rc, _, _ = self.run_cli(["init", "--yes"])
        self.assertEqual(rc, 0)
        self.assertEqual(self._config()["routing"]["preference"],
                         ["claude", "codex"])


class ModelsTests(ThrowawayHomeTestCase):
    def test_codex_models_from_observed_cache(self):
        cache = self.home / ".codex" / "models_cache.json"
        cache.parent.mkdir(parents=True)
        cache.write_text(json.dumps({"fetched_at": "2026-07-12", "models": [
            {"slug": "gpt-9", "display_name": "GPT-9",
             "supported_reasoning_levels": [{"effort": "low"},
                                            {"effort": "high"}]},
            {"slug": "gpt-9-mini"},
            "garbage", {"noslug": 1}]}))
        rc, out, _ = self.run_cli(["models", "codex"])
        self.assertEqual(rc, 0)
        self.assertIn("gpt-9  (GPT-9, efforts: low/high)", out)
        self.assertIn("gpt-9-mini", out)
        self.assertIn("observed cache", out)
        self.assertIn("pass through", out)
        self.assertEqual(tc.discover_models("codex"), ["gpt-9", "gpt-9-mini"])

    def test_codex_without_cache_degrades(self):
        rc, out, _ = self.run_cli(["models", "codex"])
        self.assertEqual(rc, 0)
        self.assertIn("any model id is accepted", out)

    def test_grok_models_passed_through_and_parsed(self):
        original = tc._grok_models_output
        tc._grok_models_output = lambda: (
            "Available models:\n  * grok-4.5 (default)\n  - grok-mini\n")
        try:
            rc, out, _ = self.run_cli(["models", "grok"])
            self.assertEqual(rc, 0)
            self.assertIn("grok-4.5", out)
            self.assertIn("passed through", out)
            self.assertEqual(tc.discover_models("grok"),
                             ["grok-4.5", "grok-mini"])
        finally:
            tc._grok_models_output = original

    def test_grok_models_failure_degrades(self):
        original = tc._grok_models_output
        tc._grok_models_output = lambda: None
        try:
            rc, out, _ = self.run_cli(["models", "grok"])
            self.assertEqual(rc, 0)
            self.assertIn("could not run", out)
        finally:
            tc._grok_models_output = original

    def test_claude_models_note_and_unknown_provider(self):
        rc, out, _ = self.run_cli(["models", "claude"])
        self.assertEqual(rc, 0)
        self.assertIn("no model-listing command", out)
        self.assertIn("sonnet", out)
        rc, _, err = self.run_cli(["models", "gpt"])
        self.assertEqual(rc, 2)
        self.assertIn("unknown provider", err)


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
        # bare integers become TOML ints (e.g. layout.lead_width)
        rc, _, _ = self.run_cli(["config", "layout.lead_width", "33"])
        self.assertEqual(rc, 0)
        data = tomllib.loads(self.cfg.read_text())
        self.assertEqual(data["layout"]["lead_width"], 33)
        self.assertIsInstance(data["layout"]["lead_width"], int)

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
        _which = tc.shutil.which
        tc.shutil.which = lambda name, *a, **k: (
            "/fake/bin/claude" if name == "claude" else None)
        seed_signin(self.home, "claude")
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


class DelegationPostureTests(ThrowawayHomeTestCase):
    """[lead] delegation: config round-trip, wizard, hook echo, texts."""

    def test_posture_helper_defaults_and_sanitizes(self):
        self.assertEqual(tc.delegation_posture(), "ask")     # no config
        self.cfg.parent.mkdir(parents=True)
        self.cfg.write_text('[lead]\ndelegation = "always"\n')
        self.assertEqual(tc.delegation_posture(), "always")
        self.cfg.write_text('[lead]\ndelegation = "yolo"\n')
        self.assertEqual(tc.delegation_posture(), "ask")     # sanitized

    def test_config_round_trip(self):
        rc, _, _ = self.run_cli(["config", "lead.delegation", "manual"])
        self.assertEqual(rc, 0)
        self.assertEqual(tc.delegation_posture(), "manual")
        rc, out, _ = self.run_cli(["config", "lead.delegation"])
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), '"manual"')

    def test_wizard_asks_and_persists_posture(self):
        _which = tc.shutil.which
        tc.shutil.which = lambda name, *a, **k: (
            "/fake/bin/claude" if name == "claude" else None)
        seed_signin(self.home, "claude")
        try:
            # plain path: model, effort, voice, LEAD=always, write
            rc, out, _ = self.run_cli(
                ["init", "--custom"], answers=["", "", "", "always", "y"])
            self.assertEqual(rc, 0)
            self.assertIn("lead", out)
            self.assertEqual(
                tomllib.loads(self.cfg.read_text())["lead"]["delegation"],
                "always")
            # --yes writes the default posture
            rc, _, _ = self.run_cli(["init", "--yes"])
            self.assertEqual(rc, 0)
            self.assertEqual(
                tomllib.loads(self.cfg.read_text())["lead"]["delegation"],
                "ask")
        finally:
            tc.shutil.which = _which

    def test_hook_echo_reports_live_posture(self):
        import subprocess
        env = dict(os.environ)
        env["HOME"] = str(self.home)
        r = subprocess.run(["sh", "-c", tc.LEAD_HOOK_COMMAND],
                           capture_output=True, text=True, env=env, timeout=15)
        self.assertEqual(r.returncode, 0)
        self.assertIn("delegation=ask", r.stdout)            # missing config
        self.cfg.parent.mkdir(parents=True)
        self.cfg.write_text('[lead]\ndelegation = "manual"\n')
        r = subprocess.run(["sh", "-c", tc.LEAD_HOOK_COMMAND],
                           capture_output=True, text=True, env=env, timeout=15)
        self.assertIn("delegation=manual", r.stdout)
        self.assertIn("teamctl-lead", r.stdout)              # detection marker

    def test_behavioral_texts_contain_ask_once_and_escalation(self):
        for text in (tc.LEAD_SKILL_MD, tc.LEAD_CLAUDE_BLOCK):
            self.assertIn("lead.delegation", text)
            self.assertIn("ONE", text.upper())               # once-per-session
            self.assertIn("never nag", text.lower())
        flat = " ".join(tc.LEAD_SKILL_MD.split())            # unwrap lines
        self.assertIn("Want me to use teamctl agent teams", flat)
        self.assertIn("I can remember this", flat)
        self.assertIn("want me to spin up a teamctl team", flat)

    def test_lead_status_shows_posture(self):
        self.cfg.parent.mkdir(parents=True)
        self.cfg.write_text('[lead]\ndelegation = "always"\n')
        rc, out, _ = self.run_cli(["lead", "status"])
        self.assertEqual(rc, 0)
        self.assertIn("delegation posture: always", out)


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
