"""v0.5.0 teammate status detection: busy / needs-input / idle.

The waiting_patterns fixtures below are synthetic pane text modeled on
each provider's approval-dialog shapes (OBSERVED-ONLY TUI text). The
claude idle fixture reproduces a REAL captured idle screen (2026-07-12,
incl. the bare `❯` input caret) — the calibration that proved the
patterns don't false-positive on a teammate at rest.

Run with:  python3 -m unittest tests.test_status
"""

import contextlib
import importlib.util
import io
import json
import os
import shlex
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEAMCTL = HERE.parent / "orchestrator"

loader = SourceFileLoader("teamctl_status", str(TEAMCTL))
spec = importlib.util.spec_from_loader("teamctl_status", loader)
tc = importlib.util.module_from_spec(spec)
loader.exec_module(tc)


CLAUDE_IDLE = """\
────────────────────────────────────────────────
❯
────────────────────────────────────────────────
  Fable 5 · high                             /rc
  ⏵⏵ bypass permissions on (shift+tab to cycle)
"""

CLAUDE_PERMISSION = """\
  Do you want to make this edit to config.py?
  ❯ 1. Yes
    2. Yes, allow all edits during this session
    3. No, and tell Claude what to do differently
"""

CODEX_APPROVAL = """\
  Allow command?
    $ rm -rf build/
  Approve [y/N]
"""

GROK_APPROVAL = """\
  grok wants to run: git push origin main
  Allow this command? [y/N]
"""

GEMINI_CONFIRM = """\
  Apply this change?
  ● 1. Yes, allow once
    2. Yes, allow always
    3. No (esc)
  Waiting for user confirmation...
"""

PLAIN_OUTPUT = """\
compiling module 12 of 40
warning: unused variable 'x'
tests passed: 118
"""


class MatchWaitingTests(unittest.TestCase):
    def _pats(self, provider):
        return tc._waiting_patterns(provider)

    def test_claude_permission_dialog_matches(self):
        hit = tc._match_waiting(CLAUDE_PERMISSION, self._pats("claude"))
        self.assertIsNotNone(hit)
        self.assertIn("Do you want", hit)

    def test_claude_real_idle_screen_is_clean(self):
        # the captured real idle screen: bare ❯ caret must NOT read as a
        # pending approval
        self.assertIsNone(
            tc._match_waiting(CLAUDE_IDLE, self._pats("claude")))

    def test_codex_and_grok_approvals_match(self):
        self.assertIsNotNone(
            tc._match_waiting(CODEX_APPROVAL, self._pats("codex")))
        self.assertIsNotNone(
            tc._match_waiting(GROK_APPROVAL, self._pats("grok")))

    def test_gemini_confirmation_matches(self):
        self.assertIsNotNone(
            tc._match_waiting(GEMINI_CONFIRM, self._pats("gemini")))

    def test_plain_output_never_matches(self):
        for prov in ("claude", "codex", "grok", "gemini", "shell"):
            self.assertIsNone(
                tc._match_waiting(PLAIN_OUTPUT, self._pats(prov)), prov)

    def test_shell_has_no_patterns(self):
        self.assertEqual(self._pats("shell"), [])

    def test_broken_pattern_is_skipped_not_fatal(self):
        self.assertIsNone(tc._match_waiting("anything", ["([broken"]))

    def test_only_the_tail_is_considered(self):
        # an approval scrolled far off-screen is history, not a live prompt
        text = CLAUDE_PERMISSION + ("\nline\n" * 30) + PLAIN_OUTPUT
        self.assertIsNone(tc._match_waiting(text, self._pats("claude")))


class PaneActivityTests(unittest.TestCase):
    def setUp(self):
        self._capture = tc._capture_pane

    def tearDown(self):
        tc._capture_pane = self._capture

    def _feed(self, *frames):
        it = iter(frames)
        last = frames[-1]
        tc._capture_pane = lambda pane: next(it, last)

    def test_changing_content_is_busy(self):
        self._feed("thinking.", "thinking..")
        state, _ = tc._pane_activity("%1", "claude", settle=0.01)
        self.assertEqual(state, "busy")

    def test_stable_dialog_is_needs_input_with_the_line(self):
        self._feed(CLAUDE_PERMISSION, CLAUDE_PERMISSION)
        state, detail = tc._pane_activity("%1", "claude", settle=0.01)
        self.assertEqual(state, "needs-input")
        self.assertIn("Do you want", detail)

    def test_stable_plain_content_is_idle(self):
        self._feed(PLAIN_OUTPUT, PLAIN_OUTPUT)
        state, _ = tc._pane_activity("%1", "claude", settle=0.01)
        self.assertEqual(state, "idle")

    def test_unknown_tui_degrades_to_idle(self):
        # a provider orchestrator has no patterns for: stable + unrecognized
        # content must never produce a wrong strong claim
        self._feed("some strange tui ▓▓▓", "some strange tui ▓▓▓")
        state, _ = tc._pane_activity("%1", "shell", settle=0.01)
        self.assertEqual(state, "idle")


class _StatusSandbox(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmpdir.name)
        os.environ["TEAMCTL_STATE"] = str(self.dir / "state.json")
        self._reconcile = tc.reconcile
        self._live = tc.live_pane_ids
        self._activity = tc._pane_activity
        self._config = tc.load_config
        tc.reconcile = lambda state: state
        tc.live_pane_ids = lambda: {"%1"}
        tc.load_config = lambda: {}

    def tearDown(self):
        tc.reconcile = self._reconcile
        tc.live_pane_ids = self._live
        tc._pane_activity = self._activity
        tc.load_config = self._config
        os.environ.pop("TEAMCTL_STATE", None)
        self.tmpdir.cleanup()

    def seed(self):
        hd = self.dir / "worker"
        hd.mkdir(exist_ok=True)
        (hd / "status").write_text("DONE 0\n")
        tc.save_state({"teammates": {
            "chatty": {"provider": "claude", "pane_id": "%1",
                       "cwd": str(self.dir), "mode": "interactive",
                       "created_at": "2026-01-01T00:00:00"},
            "worker": {"provider": "shell", "pane_id": "",
                       "cwd": str(self.dir), "mode": "dispatch",
                       "handoff": str(hd),
                       "created_at": "2026-01-01T00:00:00"},
        }})

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = tc.main(list(argv))
        return rc, out.getvalue(), err.getvalue()


class CmdStatusTests(_StatusSandbox):
    def test_status_json_shape(self):
        self.seed()
        tc._pane_activity = lambda pane, prov, settle=0.7: ("needs-input",
                                                            "Do you want?")
        rc, out, _ = self.run_cli("status", "--json")
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["chatty"]["state"], "needs-input")
        self.assertEqual(data["chatty"]["detail"], "Do you want?")
        self.assertEqual(data["chatty"]["mode"], "interactive")
        self.assertEqual(data["worker"]["state"], "done")   # lifecycle kept
        self.assertIsNone(data["worker"]["detail"])

    def test_status_table_and_single_role(self):
        self.seed()
        tc._pane_activity = lambda pane, prov, settle=0.7: ("busy", "")
        rc, out, _ = self.run_cli("status")
        self.assertEqual(rc, 0)
        self.assertIn("chatty", out)
        self.assertIn("busy", out)
        self.assertIn("done", out)
        rc, out, _ = self.run_cli("status", "chatty")
        self.assertEqual(rc, 0)
        self.assertNotIn("worker", out)

    def test_status_unknown_role_is_honest(self):
        self.seed()
        rc, _, err = self.run_cli("status", "ghost")
        self.assertEqual(rc, 1)
        self.assertIn("no teammate 'ghost'", err)

    def test_status_empty_roster(self):
        tc.save_state({"teammates": {}})
        rc, out, _ = self.run_cli("status")
        self.assertEqual(rc, 0)
        self.assertIn("no active teammates", out)


class NotifyHookTests(_StatusSandbox):
    def _install_hook(self):
        self.log = self.dir / "hook.log"
        script = self.dir / "hook.py"
        script.write_text(
            "import os, pathlib\n"
            "pathlib.Path(os.environ['HOOK_LOG']).open('a').write(\n"
            "    os.environ['TEAMCTL_ROLE'] + ' '\n"
            "    + os.environ['TEAMCTL_PREV_STATE'] + '->'\n"
            "    + os.environ['TEAMCTL_MATE_STATE'] + '\\n')\n")
        os.environ["HOOK_LOG"] = str(self.log)
        cmd = f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"
        tc.load_config = lambda: {"notify": {"command": cmd}}

    def tearDown(self):
        os.environ.pop("HOOK_LOG", None)
        super().tearDown()

    def test_transition_fires_hook_with_env(self):
        self.seed()
        self._install_hook()
        tc._pane_activity = lambda pane, prov, settle=0.7: ("idle", "")
        rc, _, _ = self.run_cli("status")           # first sighting: no fire
        self.assertEqual(rc, 0)
        self.assertFalse(self.log.exists())
        tc._pane_activity = lambda pane, prov, settle=0.7: ("needs-input",
                                                            "Approve [y/N]")
        rc, _, _ = self.run_cli("status")           # transition: fires
        self.assertEqual(rc, 0)
        self.assertEqual(self.log.read_text(),
                         "chatty idle->needs-input\n")
        rc, _, _ = self.run_cli("status")           # unchanged: silent
        self.assertEqual(self.log.read_text(),
                         "chatty idle->needs-input\n")

    def test_env_var_name_never_shadows_state_override(self):
        # the hook env carries TEAMCTL_MATE_STATE — NOT TEAMCTL_STATE,
        # which already means "state-file path override": a hook that
        # calls orchestrator back must keep resolving the right state file
        self.seed()
        self._install_hook()
        seen = {}
        real_run = tc.subprocess.run

        def spy(argv, **kw):
            seen.update(kw.get("env") or {})
            return real_run(argv, **kw)

        tc.subprocess.run = spy
        try:
            tc._fire_notify("chatty", "busy", "idle")
        finally:
            tc.subprocess.run = real_run
        self.assertEqual(seen.get("TEAMCTL_MATE_STATE"), "busy")
        self.assertEqual(seen.get("TEAMCTL_PREV_STATE"), "idle")
        self.assertEqual(seen.get("TEAMCTL_STATE"),
                         str(self.dir / "state.json"))   # untouched

    def test_broken_hook_never_breaks_status(self):
        self.seed()
        tc.load_config = lambda: {"notify":
                                  {"command": "/nonexistent/hook-bin"}}
        tc._pane_activity = lambda pane, prov, settle=0.7: ("idle", "")
        self.run_cli("status")
        tc._pane_activity = lambda pane, prov, settle=0.7: ("busy", "")
        rc, out, err = self.run_cli("status")
        self.assertEqual(rc, 0)                     # status still works
        self.assertIn("notify hook failed", err)    # and says why

    def test_departed_role_is_dropped_from_cache(self):
        self.seed()
        tc._pane_activity = lambda pane, prov, settle=0.7: ("idle", "")
        self.run_cli("status")
        cache = json.loads((self.dir / "status-cache.json").read_text())
        self.assertIn("chatty", cache)
        tc.save_state({"teammates": {}})
        self.run_cli("status")
        cache = json.loads((self.dir / "status-cache.json").read_text())
        self.assertEqual(cache, {})


@unittest.skipUnless(os.environ.get("TMUX"), "requires a live tmux session")
class LiveStatusTests(unittest.TestCase):
    """Real panes: a printing loop reads busy, a resting prompt reads
    idle, and `list` flags nothing for a plain shell."""

    def setUp(self):
        self.statedir = tempfile.TemporaryDirectory(prefix="teamctl-st-")
        os.environ["TEAMCTL_STATE"] = str(Path(self.statedir.name)
                                          / "state.json")
        self._wt = tc.worktree_settings
        tc.worktree_settings = lambda: {"enabled": False, "dir": "",
                                        "branch_prefix": "orchestrator/",
                                        "cleanup": "auto"}
        out = tc.tmux("new-window", "-d", "-n", f"teamctl-st-{os.getpid()}",
                      "-P", "-F", "#{window_id} #{pane_id}").stdout.split()
        self.window_id, self.lead_pane = out[0], out[1]
        self._tmux_pane = os.environ.get("TMUX_PANE")
        os.environ["TMUX_PANE"] = self.lead_pane

    def tearDown(self):
        for role in list(tc.load_state()["teammates"]):
            tc.main(["shutdown", role])
        tc.tmux("kill-window", "-t", self.window_id, check=False)
        tc.worktree_settings = self._wt
        if self._tmux_pane is None:
            os.environ.pop("TMUX_PANE", None)
        else:
            os.environ["TMUX_PANE"] = self._tmux_pane
        os.environ.pop("TEAMCTL_STATE", None)
        self.statedir.cleanup()

    def _status_json(self, role):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = tc.main(["status", role, "--json"])
        return rc, json.loads(out.getvalue())

    def _wait_state(self, role, want, timeout=25.0):
        # poll-for-state, never sleep-and-assert: how long a fresh shell
        # takes to settle (rc files, prompt paint) depends entirely on the
        # machine's load — the classifier honestly reads 'busy' until the
        # pane stops changing, and guessing a settle time was observed
        # flaky under real load. A wrong terminal state still fails: the
        # classifier can't reach `want` within the window.
        import time as _t
        deadline = _t.monotonic() + timeout
        last = None
        while _t.monotonic() < deadline:
            _rc, data = self._status_json(role)
            last = data[role]["state"]
            if last == want:
                return last
            _t.sleep(0.5)
        return last

    def test_busy_then_idle_detected_on_a_real_pane(self):
        rc = tc.main(["spawn", "st_mate", "--provider", "shell"])
        self.assertEqual(rc, 0)
        pane = tc.load_state()["teammates"]["st_mate"]["pane_id"]
        # a fresh shell settles to idle
        self.assertEqual(self._wait_state("st_mate", "idle"), "idle")
        # a printing loop makes the pane content move -> busy
        tc.tmux("send-keys", "-t", pane, "-l", "--",
                "while true; do date; sleep 0.2; done", check=False)
        tc.tmux("send-keys", "-t", pane, "C-m", check=False)
        self.assertEqual(self._wait_state("st_mate", "busy", 10.0), "busy")
        # stop the loop -> back to a resting prompt
        tc.tmux("send-keys", "-t", pane, "C-c", check=False)
        self.assertEqual(self._wait_state("st_mate", "idle"), "idle")


if __name__ == "__main__":
    unittest.main()
