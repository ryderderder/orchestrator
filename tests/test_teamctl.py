"""Tests for the teamctl agent-teammate control CLI.

Pure logic (state, reconcile, dry-run, duplicate guard, provider registry,
routing, the init wizard) runs anywhere. Live spawn/list/shutdown against
real tmux panes runs only when executed inside a tmux session.

Run with:  python3 -m unittest discover -s tests
"""

import importlib.util
import json
import os
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEAMCTL = HERE.parent / "teamctl"

# teamctl has no .py extension, so load it via an explicit source loader.
loader = SourceFileLoader("teamctl", str(TEAMCTL))
spec = importlib.util.spec_from_loader("teamctl", loader)
tc = importlib.util.module_from_spec(spec)
loader.exec_module(tc)


class StateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = HERE / ".test-state.json"
        os.environ["TEAMCTL_STATE"] = str(self.tmp)
        self.tmp.unlink(missing_ok=True)

    def tearDown(self):
        self.tmp.unlink(missing_ok=True)
        Path(str(self.tmp) + ".tmp").unlink(missing_ok=True)
        os.environ.pop("TEAMCTL_STATE", None)

    def test_state_path_override(self):
        self.assertEqual(tc.state_path(), self.tmp)

    def test_load_empty_and_roundtrip(self):
        self.assertEqual(tc.load_state(), {"teammates": {}})
        tc.save_state({"teammates": {"r": {"pane_id": "%1"}}})
        self.assertEqual(tc.load_state()["teammates"]["r"]["pane_id"], "%1")

    def test_load_corrupt_state_is_safe(self):
        self.tmp.write_text("{not json")
        self.assertEqual(tc.load_state(), {"teammates": {}})

    def test_reconcile_drops_dead_panes(self):
        tc.save_state({"teammates": {
            "alive": {"pane_id": "%999999"},
            "dead": {"pane_id": "%nonexistent"},
        }})
        state = tc.reconcile(tc.load_state())
        # neither pane really exists, so both are dropped
        self.assertEqual(state["teammates"], {})


class ProviderTests(unittest.TestCase):
    def test_all_expected_providers_registered(self):
        for p in ("claude", "codex", "grok", "shell"):
            self.assertIn(p, tc.PROVIDERS)

    def test_grok_launch_shape(self):
        self.assertEqual(tc.PROVIDERS["grok"], ["grok"])

    def test_headless_argv_includes_model_and_effort(self):
        a = tc.headless_argv("claude", "do it", "opus", "high")
        self.assertIn("-p", a)
        self.assertIn("--output-format", a)
        self.assertEqual(a[a.index("--model") + 1], "opus")
        self.assertEqual(a[a.index("--effort") + 1], "high")
        g = tc.headless_argv("grok", "t", "grok-4.5", "high")
        self.assertEqual(g[g.index("-m") + 1], "grok-4.5")
        c = tc.headless_argv("codex", "t", "gpt-5.6", "xhigh")
        self.assertIn("exec", c)
        self.assertTrue(any("model_reasoning_effort" in x for x in c))

    def test_classify_output(self):
        self.assertEqual(tc.classify_output("You've hit your usage limit"), "exhausted")
        self.assertEqual(tc.classify_output("Error: unauthorized"), "auth-error")
        self.assertEqual(tc.classify_output("here is your answer"), "ok")


class SignalExpiryTests(unittest.TestCase):
    def test_live_signal_respects_reset_time(self):
        import time as _t
        future = {"signal": "exhausted", "resets_at": _t.time() + 3600}
        past = {"signal": "exhausted", "resets_at": _t.time() - 60}
        no_reset = {"signal": "exhausted"}
        self.assertEqual(tc._live_signal(future), "exhausted")
        self.assertIsNone(tc._live_signal(past))          # auto-expired
        self.assertEqual(tc._live_signal(no_reset), "exhausted")
        self.assertIsNone(tc._live_signal(None))


class UsageTests(unittest.TestCase):
    def setUp(self):
        # keep the providers.json cache away from the real state dir
        self.tmp = HERE / ".test-usage-state.json"
        os.environ["TEAMCTL_STATE"] = str(self.tmp)

    def tearDown(self):
        for p in (self.tmp, HERE / "providers.json"):
            p.unlink(missing_ok=True)
        os.environ.pop("TEAMCTL_STATE", None)

    def test_find_key_nested(self):
        blob = {"a": {"b": [{"rate_limits": {"primary": {"used_percent": 42}}}]}}
        rl = tc._find_key(blob, "rate_limits")
        self.assertEqual(rl["primary"]["used_percent"], 42)

    def test_find_key_absent(self):
        self.assertIsNone(tc._find_key({"x": 1}, "rate_limits"))

    def test_fmt_reset(self):
        now = 1_000_000
        # 2h05m in the future
        s = tc._fmt_reset(now + (2 * 3600 + 5 * 60), now)
        self.assertIn("2h05m", s)
        # already passed
        self.assertIn("now", tc._fmt_reset(now - 10, now))
        # unknown
        self.assertEqual(tc._fmt_reset(None, now), "?")

    def test_usage_json_runs(self):
        # should not raise even if no codex logs are present
        self.assertEqual(tc.main(["usage", "--json"]), 0)


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = HERE / ".probe-state.json"
        os.environ["TEAMCTL_STATE"] = str(self.tmp)

    def tearDown(self):
        for p in (self.tmp, HERE / "providers.json"):
            p.unlink(missing_ok=True)
        os.environ.pop("TEAMCTL_STATE", None)

    def test_providers_reports_rows(self):
        # should run and classify each provider without error
        self.assertEqual(tc.main(["providers", "--json"]), 0)


class VersionTests(unittest.TestCase):
    def test_version_flag(self):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit) as cm:
            tc.main(["--version"])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn(tc.VERSION, buf.getvalue())
        self.assertEqual(tc.VERSION, "0.2.0")


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = HERE / ".test-cli-state.json"
        os.environ["TEAMCTL_STATE"] = str(self.tmp)
        self.tmp.unlink(missing_ok=True)

    def tearDown(self):
        self.tmp.unlink(missing_ok=True)
        Path(str(self.tmp) + ".tmp").unlink(missing_ok=True)
        os.environ.pop("TEAMCTL_STATE", None)

    def test_unknown_provider_rejected(self):
        rc = tc.main(["spawn", "r", "--provider", "bogus"])
        self.assertEqual(rc, 2)

    def test_list_empty(self):
        self.assertEqual(tc.main(["list"]), 0)

    def test_shutdown_missing_role(self):
        self.assertEqual(tc.main(["shutdown", "ghost"]), 1)

    def test_send_missing_role(self):
        self.assertEqual(tc.main(["send", "ghost", "hi"]), 1)

    def test_dry_run_works_without_tmux(self):
        # dry-run must not require a tmux session
        saved = os.environ.pop("TMUX", None)
        try:
            rc = tc.main(["spawn", "r", "--provider", "grok",
                          "--prompt", "hi", "--cwd", str(HERE), "--dry-run"])
            self.assertEqual(rc, 0)
        finally:
            if saved is not None:
                os.environ["TMUX"] = saved

    def test_build_launch_line_quotes_values(self):
        line = tc.build_launch_line("grok", "fix; rm -rf /", "/a b")
        # the injected shell metacharacters must be quoted, not live
        self.assertIn("'fix; rm -rf /'", line)
        self.assertIn("'/a b'", line)

    def test_spawn_model_effort_reach_launch_line(self):
        # dry-run so no tmux needed; model/effort must appear as flags
        saved = os.environ.pop("TMUX", None)
        try:
            import io
            import contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = tc.main(["spawn", "r", "--provider", "grok",
                              "--model", "grok-4.5", "--effort", "high", "--dry-run"])
            self.assertEqual(rc, 0)
            out = buf.getvalue()
            self.assertIn("grok-4.5", out)
            self.assertIn("high", out)
        finally:
            if saved is not None:
                os.environ["TMUX"] = saved


class TmuxMissingTests(unittest.TestCase):
    def test_clean_error_when_tmux_absent(self):
        original = tc.subprocess.run

        def boom(*a, **k):
            raise FileNotFoundError("tmux")

        tc.subprocess.run = boom
        try:
            with self.assertRaises(tc.TeamctlError):
                tc.tmux("list-panes")
        finally:
            tc.subprocess.run = original


class RouteTests(unittest.TestCase):
    """Deterministic routing: availability is driven by monkeypatched which/
    AUTH_PATHS/load_config plus a fake providers.json under a temp state dir.
    All selection tests use --dry-run so no tmux is needed."""

    def setUp(self):
        import tempfile
        self.tmpdir = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmpdir.name)
        os.environ["TEAMCTL_STATE"] = str(self.dir / "state.json")

        self._which = tc.shutil.which
        self._auth = tc.AUTH_PATHS
        self._config = tc.load_config

        # default fixture: all three installed and authed, no cached signals
        self.installed = {"claude", "codex", "grok"}
        tc.shutil.which = lambda name, *a, **k: (
            f"/fake/bin/{name}" if name in self.installed else None)
        tc.AUTH_PATHS = {}
        for prov in ("claude", "codex", "grok"):
            p = self.dir / f"auth-{prov}"
            p.write_text("x")
            tc.AUTH_PATHS[prov] = p
        tc.load_config = lambda: {}

    def tearDown(self):
        tc.shutil.which = self._which
        tc.AUTH_PATHS = self._auth
        tc.load_config = self._config
        os.environ.pop("TEAMCTL_STATE", None)
        self.tmpdir.cleanup()

    def _write_signals(self, signals: dict):
        payload = {p: {"signal": s, "at": "2026-01-01T00:00:00"}
                   for p, s in signals.items()}
        (self.dir / "providers.json").write_text(json.dumps(payload))

    def _route(self, *extra):
        import io
        import contextlib
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = tc.main(["route", "r", "--task", "do it", "--dry-run", *extra])
        return rc, out.getvalue(), err.getvalue()

    def test_default_preference_picks_claude(self):
        rc, out, _ = self._route()
        self.assertEqual(rc, 0)
        self.assertIn("route: selected claude", out)
        self.assertIn("dry-run: claude -p", out)

    def test_exhausted_provider_is_skipped(self):
        self._write_signals({"claude": "exhausted"})
        rc, out, _ = self._route()
        self.assertEqual(rc, 0)
        self.assertIn("route: selected codex", out)
        self.assertIn("claude: exhausted", out)

    def test_auth_error_signal_is_skipped(self):
        self._write_signals({"claude": "auth-error", "codex": "exhausted"})
        rc, out, _ = self._route()
        self.assertEqual(rc, 0)
        self.assertIn("route: selected grok", out)

    def test_providers_flag_restricts_candidates(self):
        rc, out, _ = self._route("--providers", "grok")
        self.assertEqual(rc, 0)
        self.assertIn("route: selected grok", out)

    def test_config_preference_order_respected(self):
        tc.load_config = lambda: {"routing": {"preference": ["grok", "claude", "codex"]}}
        rc, out, _ = self._route()
        self.assertEqual(rc, 0)
        self.assertIn("route: selected grok", out)

    def test_all_excluded_fails_with_reasons(self):
        self.installed.discard("claude")               # not-installed
        tc.AUTH_PATHS["codex"].unlink()                # not-authed
        self._write_signals({"grok": "exhausted"})     # exhausted
        rc, _, err = self._route()
        self.assertNotEqual(rc, 0)
        self.assertIn("no available provider", err)
        self.assertIn("claude: not-installed", err)
        self.assertIn("codex: not-authed", err)
        self.assertIn("grok: exhausted", err)

    def test_dry_run_needs_no_tmux_and_prints_launch_line(self):
        saved = os.environ.pop("TMUX", None)
        try:
            rc, out, _ = self._route("--model", "opus", "--effort", "high")
            self.assertEqual(rc, 0)
            self.assertIn("--model opus", out)
            self.assertIn("--effort high", out)
        finally:
            if saved is not None:
                os.environ["TMUX"] = saved


class InitTests(unittest.TestCase):
    """`teamctl init` wizard, run entirely against a throwaway HOME."""

    def setUp(self):
        import tempfile
        self.tmpdir = tempfile.TemporaryDirectory()
        self.home = Path(self.tmpdir.name)
        self._home_env = os.environ.get("HOME")
        os.environ["HOME"] = str(self.home)

        self._which = tc.shutil.which
        self._auth = tc.AUTH_PATHS
        self._input = tc._input

        # fixture: only claude is installed and authed
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
        tc._input = self._input
        if self._home_env is not None:
            os.environ["HOME"] = self._home_env
        self.tmpdir.cleanup()

    def _run_init(self, answers=None, *extra):
        if answers is not None:
            it = iter(answers)
            tc._input = lambda prompt: next(it)
        import io
        import contextlib
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = tc.main(["init", *extra])
        return rc, out.getvalue()

    def _config(self):
        import tomllib
        path = self.home / ".config" / "agent-team" / "config.toml"
        self.assertTrue(path.exists(), "config.toml was not written")
        return tomllib.loads(path.read_text())

    def test_yes_writes_defaults_and_touches_nothing_else(self):
        rc, out = self._run_init(None, "--yes")
        self.assertEqual(rc, 0)
        cfg = self._config()
        self.assertEqual(cfg["output"]["verbosity"], "normal")
        # blank model/effort => the provider section carries no keys
        self.assertEqual(cfg.get("providers", {}).get("claude", {}), {})
        # --yes must not touch tmux.conf or Claude Code settings
        self.assertFalse((self.home / ".tmux.conf").exists())
        self.assertFalse((self.home / ".claude" / "settings.json").exists())
        self.assertIn("Summary of changes", out)

    def test_scripted_answers_reach_config(self):
        # answers: claude model, claude effort, verbosity, tmux y/n, statusline y/n
        rc, out = self._run_init(["opus", "high", "terse", "n", "n"])
        self.assertEqual(rc, 0)
        cfg = self._config()
        self.assertEqual(cfg["providers"]["claude"]["model"], "opus")
        self.assertEqual(cfg["providers"]["claude"]["effort"], "high")
        self.assertEqual(cfg["output"]["verbosity"], "terse")
        self.assertIn("revert", out)

    def test_rerun_backs_up_previous_config(self):
        rc, _ = self._run_init(["opus", "high", "normal", "n", "n"])
        self.assertEqual(rc, 0)
        rc, _ = self._run_init(["sonnet", "", "normal", "n", "n"])
        self.assertEqual(rc, 0)
        self.assertEqual(self._config()["providers"]["claude"]["model"], "sonnet")
        bak = self.home / ".config" / "agent-team" / "config.toml.bak-teamctl"
        self.assertTrue(bak.exists())
        self.assertIn('model = "opus"', bak.read_text())

    def test_tmux_block_appended_once_and_backed_up(self):
        conf = self.home / ".tmux.conf"
        conf.write_text("set -g mouse on\n")
        rc, _ = self._run_init(["", "", "", "y", "n"])
        self.assertEqual(rc, 0)
        text = conf.read_text()
        self.assertEqual(text.count(tc.TMUX_MARKER_BEGIN), 1)
        self.assertEqual(text.count(tc.TMUX_MARKER_END), 1)
        self.assertIn("set -g mouse on", text)          # original preserved
        self.assertIn("pane-border-format", text)
        self.assertTrue((self.home / ".tmux.conf.bak-teamctl").exists())
        # second accept must not duplicate the block
        rc, out = self._run_init(["", "", "", "y", "n"])
        self.assertEqual(rc, 0)
        self.assertEqual(conf.read_text().count(tc.TMUX_MARKER_BEGIN), 1)
        self.assertIn("skipping", out)

    def test_statusline_settings_added_minimally_and_skipped_if_present(self):
        settings = self.home / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({"model": "opus"}, indent=2))
        rc, _ = self._run_init(["", "", "", "n", "y"])
        self.assertEqual(rc, 0)
        data = json.loads(settings.read_text())
        self.assertEqual(data["model"], "opus")          # existing keys untouched
        self.assertEqual(data["statusLine"]["type"], "command")
        self.assertIn("claude-statusline", data["statusLine"]["command"])
        self.assertTrue(
            (self.home / ".local" / "bin" / "claude-statusline").exists())
        self.assertTrue(Path(str(settings) + ".bak-teamctl").exists())
        # second run: key already present -> settings must be left alone
        before = settings.read_text()
        rc, out = self._run_init(["", "", "", "n", "y"])
        self.assertEqual(rc, 0)
        self.assertEqual(settings.read_text(), before)
        self.assertIn("already has a statusLine key", out)

    def test_statusline_creates_settings_when_absent(self):
        rc, _ = self._run_init(["", "", "", "n", "y"])
        self.assertEqual(rc, 0)
        settings = self.home / ".claude" / "settings.json"
        data = json.loads(settings.read_text())
        self.assertEqual(data["statusLine"]["command"],
                         "~/.local/bin/claude-statusline")


class ResultWaitLivenessTests(unittest.TestCase):
    """result --wait must notice a dead pane/pid instead of spinning to timeout.

    Uses TEAMCTL_STATE + the shell provider's handoff layout; reconcile is
    stubbed so a dead pane is still tracked long enough for the wait loop to
    run (the real hang is mid-wait after spawn, not pre-reconcile)."""

    def setUp(self):
        import tempfile
        self.tmpdir = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmpdir.name)
        os.environ["TEAMCTL_STATE"] = str(self.dir / "state.json")
        self._reconcile = tc.reconcile
        self._live = tc.live_pane_ids
        self._pid_alive = tc._pid_alive
        # Keep the teammate in state even when its pane is gone.
        tc.reconcile = lambda state: state

    def tearDown(self):
        tc.reconcile = self._reconcile
        tc.live_pane_ids = self._live
        tc._pid_alive = self._pid_alive
        os.environ.pop("TEAMCTL_STATE", None)
        self.tmpdir.cleanup()

    def _seed_dispatch_mate(self, role: str, pane_id: str = "%dead",
                            pid: int | None = 999_999_999) -> Path:
        hd = self.dir / role
        hd.mkdir(parents=True, exist_ok=True)
        (hd / "task.md").write_text("do a thing")
        if pid is not None:
            (hd / "pid").write_text(str(pid))
        # no status file => still "running"
        tc.save_state({"teammates": {
            role: {
                "provider": "shell",
                "pane_id": pane_id,
                "cwd": str(self.dir),
                "model": "",
                "effort": "",
                "mode": "dispatch",
                "handoff": str(hd),
                "created_at": "2026-01-01T00:00:00",
            }
        }})
        return hd

    def _result(self, *extra):
        import io
        import contextlib
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = tc.main(["result", *extra])
        return rc, out.getvalue(), err.getvalue()

    def test_teammate_alive_prefers_live_pane(self):
        hd = self._seed_dispatch_mate("m", pane_id="%1", pid=None)
        tc.live_pane_ids = lambda: {"%1"}
        self.assertTrue(tc._teammate_alive(
            tc.load_state()["teammates"]["m"], hd))

    def test_teammate_alive_via_wrapper_pid(self):
        hd = self._seed_dispatch_mate("m", pane_id="%gone", pid=os.getpid())
        tc.live_pane_ids = lambda: set()
        tc._pid_alive = lambda p: p == os.getpid()
        self.assertTrue(tc._teammate_alive(
            tc.load_state()["teammates"]["m"], hd))

    def test_teammate_dead_when_pane_and_pid_gone(self):
        hd = self._seed_dispatch_mate("m", pane_id="%gone", pid=42)
        tc.live_pane_ids = lambda: set()
        tc._pid_alive = lambda p: False
        self.assertFalse(tc._teammate_alive(
            tc.load_state()["teammates"]["m"], hd))

    def test_wait_fails_fast_when_teammate_died_no_status(self):
        import time as _t
        self._seed_dispatch_mate("dead_mate", pane_id="%gone", pid=42)
        tc.live_pane_ids = lambda: set()
        tc._pid_alive = lambda p: False

        t0 = _t.monotonic()
        rc, _, err = self._result("dead_mate", "--wait", "--timeout", "30")
        elapsed = _t.monotonic() - t0

        self.assertEqual(rc, 1)
        self.assertIn("failed (teammate died before writing status)", err)
        # Must not burn the full --timeout waiting on a corpse.
        self.assertLess(elapsed, 5.0)

    def test_wait_succeeds_if_status_lands_before_liveness_check(self):
        # Status written by a normal exit wins over a vanishing pane.
        hd = self._seed_dispatch_mate("done_mate", pane_id="%gone", pid=42)
        (hd / "status").write_text("DONE 0\n")
        (hd / "result.json").write_text('{"ok": true}')
        tc.live_pane_ids = lambda: set()
        tc._pid_alive = lambda p: False

        rc, out, err = self._result("done_mate", "--wait", "--timeout", "5")
        self.assertEqual(rc, 0)
        self.assertIn("done_mate: done", out)
        self.assertNotIn("died before writing status", err)


@unittest.skipUnless(os.environ.get("TMUX"), "requires a live tmux session")
class LiveTmuxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = HERE / ".test-live-state.json"
        os.environ["TEAMCTL_STATE"] = str(self.tmp)
        self.tmp.unlink(missing_ok=True)

    def tearDown(self):
        # best-effort cleanup of any pane we left behind
        for role in ("t_alpha", "t_beta", "rt_mate", "orphan_mate", "kill_mate"):
            tc.main(["shutdown", role])
        self.tmp.unlink(missing_ok=True)
        Path(str(self.tmp) + ".tmp").unlink(missing_ok=True)
        os.environ.pop("TEAMCTL_STATE", None)

    @staticmethod
    def _active_pane() -> str:
        # the ACTIVE pane of the current window (display-message with no -t
        # would resolve to the invoking pane, not the active one)
        out = tc.tmux("list-panes", "-F", "#{pane_id} #{pane_active}").stdout
        for line in out.splitlines():
            pane, active = line.split()
            if active == "1":
                return pane
        return ""

    def test_spawn_does_not_steal_focus(self):
        # regression: split-window without -d moves the user's cursor into
        # the new teammate pane; spawn must leave the active pane alone.
        before = self._active_pane()
        self.assertEqual(tc.main(["spawn", "t_alpha", "--provider", "shell"]), 0)
        try:
            after = self._active_pane()
            spawned = tc.load_state()["teammates"]["t_alpha"]["pane_id"]
            self.assertNotEqual(after, spawned, "focus moved to the new pane")
            self.assertEqual(before, after, "active pane changed during spawn")
        finally:
            tc.main(["shutdown", "t_alpha"])

    def test_spawn_list_duplicate_shutdown(self):
        self.assertEqual(tc.main(["spawn", "t_alpha", "--provider", "shell"]), 0)
        state = tc.load_state()
        self.assertIn("t_alpha", state["teammates"])
        pane = state["teammates"]["t_alpha"]["pane_id"]
        self.assertIn(pane, tc.live_pane_ids())

        # duplicate role refused
        self.assertEqual(tc.main(["spawn", "t_alpha", "--provider", "shell"]), 1)

        # shutdown removes it and closes the pane
        self.assertEqual(tc.main(["shutdown", "t_alpha"]), 0)
        self.assertNotIn("t_alpha", tc.load_state()["teammates"])
        self.assertNotIn(pane, tc.live_pane_ids())

    def test_send_instruction_lands_in_pane(self):
        import time
        self.assertEqual(tc.main(["spawn", "t_beta", "--provider", "shell"]), 0)
        pane = tc.load_state()["teammates"]["t_beta"]["pane_id"]

        # wait for the shell to finish starting: capture-pane content must be
        # non-empty and stable across two reads before we send anything.
        prev, stable = None, False
        for _ in range(30):
            cur = tc.tmux("capture-pane", "-p", "-t", pane).stdout.strip()
            if cur and cur == prev:
                stable = True
                break
            prev = cur
            time.sleep(0.1)
        self.assertTrue(stable, "teammate shell never settled")

        # type a command into the teammate and submit it
        self.assertEqual(tc.main(["send", "t_beta", "echo TEAMCTL_PING_XYZ"]), 0)

        # Enter must have submitted it: the echo OUTPUT appears on its own
        # line (distinct from the typed `echo TEAMCTL_PING_XYZ` command line).
        found = False
        for _ in range(20):
            cap = tc.tmux("capture-pane", "-p", "-t", pane).stdout
            if any(line.strip() == "TEAMCTL_PING_XYZ" for line in cap.splitlines()):
                found = True
                break
            time.sleep(0.15)
        self.assertTrue(found, "instruction did not execute in the teammate pane")

    def test_dispatch_roundtrip_via_shell_provider(self):
        # a dispatched 'shell' teammate emits JSON; the lead reads it back.
        task = 'printf %s \'{"answer": 42, "ok": true}\''
        self.assertEqual(
            tc.main(["dispatch", "rt_mate", "--provider", "shell", "--task", task]), 0)

        rc = tc.main(["result", "rt_mate", "--wait", "--timeout", "20"])
        self.assertEqual(rc, 0)

        hd = tc.handoff_dir("rt_mate")
        import json as _json
        result = _json.loads((hd / "result.json").read_text())
        self.assertEqual(result["answer"], 42)
        self.assertTrue(result["ok"])
        # status file recorded a clean exit
        status, code = tc._read_status(hd)
        self.assertEqual(status, "done")
        self.assertEqual(code, 0)

    def test_teardown_kills_wrapped_process_no_orphan(self):
        # regression: a dispatched teammate whose provider is a long-lived
        # child process must be fully killed on shutdown, not orphaned.
        task = 'sleep 300'
        self.assertEqual(
            tc.main(["dispatch", "orphan_mate", "--provider", "shell", "--task", task]), 0)
        pane = tc.load_state()["teammates"]["orphan_mate"]["pane_id"]
        wrapper_pid = tc._pane_pid(pane)
        self.assertIsNotNone(wrapper_pid)

        # the sleep child should be alive under the wrapper
        import time as _t
        kids = []
        for _ in range(20):
            kids = tc._descendants(wrapper_pid)
            if kids:
                break
            _t.sleep(0.1)
        self.assertTrue(kids, "expected a live child process under the wrapper")

        self.assertEqual(tc.main(["shutdown", "orphan_mate"]), 0)
        # neither the wrapper nor any descendant may survive
        self.assertFalse(tc._pid_alive(wrapper_pid), "wrapper survived shutdown")
        for k in kids:
            self.assertFalse(tc._pid_alive(k), f"orphaned child {k} survived shutdown")

    def test_result_wait_fails_when_pane_killed_before_status(self):
        # Kill the dispatch pane mid-run: --wait must fail fast, not hang.
        import io
        import contextlib
        import time as _t

        task = "sleep 300"
        self.assertEqual(
            tc.main(["dispatch", "kill_mate", "--provider", "shell", "--task", task]), 0)
        info = tc.load_state()["teammates"]["kill_mate"]
        pane = info["pane_id"]
        hd = Path(info["handoff"])

        # Wait until the wrapper has recorded its pid (proves it started).
        for _ in range(30):
            if (hd / "pid").exists():
                break
            _t.sleep(0.1)
        self.assertTrue((hd / "pid").exists(), "wrapper never wrote pid")
        self.assertFalse((hd / "status").exists())

        # Hard-kill the pane without letting the wrapper write status.
        tc.tmux("kill-pane", "-t", pane, check=False)
        for _ in range(20):
            if pane not in tc.live_pane_ids():
                break
            _t.sleep(0.1)
        self.assertNotIn(pane, tc.live_pane_ids())

        # reconcile() would drop the dead pane; keep it tracked so the wait
        # loop is the code under test (same as a mid-wait death).
        original = tc.reconcile
        tc.reconcile = lambda state: state
        try:
            t0 = _t.monotonic()
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = tc.main(["result", "kill_mate", "--wait", "--timeout", "30"])
            elapsed = _t.monotonic() - t0
        finally:
            tc.reconcile = original

        self.assertEqual(rc, 1)
        self.assertIn("failed (teammate died before writing status)", err.getvalue())
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
