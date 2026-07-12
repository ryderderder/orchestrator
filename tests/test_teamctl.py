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


class LayoutTests(unittest.TestCase):
    """lead_width_percent clamping, split-candidate selection, and the
    resize call — all with tmux interactions monkeypatched."""

    def setUp(self):
        self._config = tc.load_config
        self._window_panes = tc._window_panes
        self._live = tc.live_pane_ids
        self._tmux = tc.tmux
        self._pane = os.environ.get("TMUX_PANE")

    def tearDown(self):
        tc.load_config = self._config
        tc._window_panes = self._window_panes
        tc.live_pane_ids = self._live
        tc.tmux = self._tmux
        if self._pane is None:
            os.environ.pop("TMUX_PANE", None)
        else:
            os.environ["TMUX_PANE"] = self._pane

    def test_lead_width_percent_clamps_and_defaults(self):
        cases = [({}, 50),
                 ({"layout": {"lead_width": 33}}, 33),
                 ({"layout": {"lead_width": "33"}}, 33),
                 ({"layout": {"lead_width": 90}}, 80),
                 ({"layout": {"lead_width": 5}}, 20),
                 ({"layout": {"lead_width": "wide"}}, 50)]
        for cfg, want in cases:
            tc.load_config = lambda cfg=cfg: cfg
            self.assertEqual(tc.lead_width_percent(), want, cfg)

    def test_split_candidates_exclude_lead_and_fall_back(self):
        tc._window_panes = lambda lead: ["%1", "%2", "%3"]
        self.assertEqual(tc._split_candidates("%1", []), ["%2", "%3"])
        # window listing empty -> tracked teammates that are still live
        tc._window_panes = lambda lead: []
        tc.live_pane_ids = lambda: {"%9"}
        self.assertEqual(tc._split_candidates("%1", ["%9", "%7"]), ["%9"])
        # no lead at all -> tracked fallback too
        self.assertEqual(tc._split_candidates(None, ["%9"]), ["%9"])

    def test_enforce_lead_width_resizes_lead_only_when_known(self):
        calls = []
        tc.tmux = lambda *a, **k: calls.append(a)
        tc.load_config = lambda: {"layout": {"lead_width": 33}}
        os.environ.pop("TMUX_PANE", None)
        tc._enforce_lead_width()
        self.assertEqual(calls, [])                     # no lead -> no resize
        os.environ["TMUX_PANE"] = "%5"
        tc._enforce_lead_width()
        self.assertEqual(calls,
                         [("resize-pane", "-t", "%5", "-x", "33%")])


class SessionCaptureTests(unittest.TestCase):
    """Exact-session id capture from dispatch artifacts (item: follow-ups
    must never resume 'the most recent session')."""

    UUID = "019f5468-ea9d-7562-a465-6d69cdd961fa"

    def setUp(self):
        import tempfile
        self.tmpdir = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmpdir.name)
        os.environ["TEAMCTL_STATE"] = str(self.dir / "state.json")
        self._home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.dir)      # isolates ~/.codex fallback
        self.hd = self.dir / "mate"
        self.hd.mkdir()

    def tearDown(self):
        if self._home is not None:
            os.environ["HOME"] = self._home
        os.environ.pop("TEAMCTL_STATE", None)
        self.tmpdir.cleanup()

    def test_codex_banner_capture(self):
        # live-verified stderr banner shape from a real dispatch error.log
        (self.hd / "error.log").write_text(
            f"[2026-07-11] OpenAI Codex v0.144\nsession id: {self.UUID}\n")
        self.assertEqual(tc._extract_session_id("codex", self.hd), self.UUID)

    def test_codex_malformed_banner_falls_back_to_rollout_filename(self):
        (self.hd / "error.log").write_text("no banner here\n")
        day = self.dir / ".codex" / "sessions" / "2026" / "07" / "11"
        day.mkdir(parents=True)
        (day / f"rollout-2026-07-11T20-39-49-{self.UUID}.jsonl").write_text("x")
        (day / "rollout-not-a-uuid.jsonl").write_text("x")
        self.assertEqual(tc._extract_session_id("codex", self.hd), self.UUID)

    def test_codex_fallback_respects_dispatch_start_time(self):
        import time as _t
        (self.hd / "error.log").write_text("no banner\n")
        day = self.dir / ".codex" / "sessions" / "2026" / "07" / "11"
        day.mkdir(parents=True)
        old = day / f"rollout-old-{self.UUID}.jsonl"
        old.write_text("x")
        past = _t.time() - 3600
        os.utime(old, (past, past))
        # the only rollout predates the dispatch -> not this dispatch's
        self.assertIsNone(
            tc._extract_session_id("codex", self.hd, since=_t.time() - 60))

    def test_claude_and_grok_ids_from_result_json(self):
        (self.hd / "result.json").write_text(
            json.dumps({"type": "result", "session_id": "abc-123"}))
        self.assertEqual(tc._extract_session_id("claude", self.hd), "abc-123")
        (self.hd / "result.json").write_text(
            json.dumps({"text": "hi", "sessionId": "xyz-9"}))
        self.assertEqual(tc._extract_session_id("grok", self.hd), "xyz-9")
        (self.hd / "result.json").write_text("{broken")
        self.assertIsNone(tc._extract_session_id("grok", self.hd))

    def test_capture_persists_and_survives_artifact_loss(self):
        info = {"provider": "grok", "created_at": "2026-01-01T00:00:00"}
        (self.hd / "result.json").write_text(json.dumps({"sessionId": "s1"}))
        self.assertEqual(tc._capture_session_id(info, self.hd), "s1")
        self.assertEqual((self.hd / "session").read_text().strip(), "s1")
        # a later turn mints a new id -> refreshed
        (self.hd / "result.json").write_text(json.dumps({"sessionId": "s2"}))
        self.assertEqual(tc._capture_session_id(info, self.hd), "s2")
        # artifacts cleared -> the persisted id still wins
        (self.hd / "result.json").unlink()
        self.assertEqual(tc._capture_session_id(info, self.hd), "s2")


class FollowupExactSessionTests(unittest.TestCase):
    """followup resumes the EXACT captured session, or refuses."""

    def setUp(self):
        import tempfile
        self.tmpdir = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmpdir.name)
        os.environ["TEAMCTL_STATE"] = str(self.dir / "state.json")
        self._tmux_env = os.environ.get("TMUX")
        os.environ["TMUX"] = "/fake/sock,1,0"
        self._reconcile = tc.reconcile
        self._dispatch = tc._dispatch_pane
        self._title = tc._set_pane_title
        tc.reconcile = lambda state: state
        self.argv_seen = []
        tc._dispatch_pane = (lambda role, hd, argv, cwd, provider, model:
                             self.argv_seen.append(argv) or "%fake")
        tc._set_pane_title = lambda *a, **k: None

    def tearDown(self):
        tc.reconcile = self._reconcile
        tc._dispatch_pane = self._dispatch
        tc._set_pane_title = self._title
        if self._tmux_env is None:
            os.environ.pop("TMUX", None)
        else:
            os.environ["TMUX"] = self._tmux_env
        os.environ.pop("TEAMCTL_STATE", None)
        self.tmpdir.cleanup()

    def _seed(self, provider="grok", session=None):
        hd = self.dir / "mate"
        hd.mkdir(exist_ok=True)
        if session:
            (hd / "session").write_text(session + "\n")
        tc.save_state({"teammates": {"mate": {
            "provider": provider, "pane_id": "%1", "cwd": str(self.dir),
            "model": "", "effort": "", "mode": "dispatch",
            "handoff": str(hd), "created_at": "2026-01-01T00:00:00"}}})
        return hd

    def _followup(self):
        import contextlib
        import io
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = tc.main(["followup", "mate", "--task", "next step"])
        return rc, out.getvalue(), err.getvalue()

    def test_followup_uses_captured_session_id(self):
        self._seed(provider="grok", session="sess-42")
        rc, _, _ = self._followup()
        self.assertEqual(rc, 0)
        argv = self.argv_seen[0]
        self.assertEqual(argv[argv.index("-r") + 1], "sess-42")
        self.assertNotIn("-c", argv)                    # no "most recent"

    def test_followup_refuses_without_session_id(self):
        self._seed(provider="codex", session=None)
        # isolate the ~/.codex rollout fallback from the real machine
        home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.dir)
        try:
            rc, _, err = self._followup()
        finally:
            os.environ["HOME"] = home
        self.assertEqual(rc, 1)
        self.assertIn("no session id captured", err)
        self.assertEqual(self.argv_seen, [])            # nothing launched

    def test_resume_argv_is_exact_session_for_all_providers(self):
        c = tc.resume_argv("codex", "task", "", "", "SID")
        self.assertEqual(c, ["codex", "exec", "resume", "SID", "task"])
        self.assertNotIn("--last", c)
        a = tc.resume_argv("claude", "task", "opus", "", "SID")
        self.assertEqual(a[a.index("--resume") + 1], "SID")
        self.assertNotIn("-c", a)
        g = tc.resume_argv("grok", "task", "", "", "SID")
        self.assertEqual(g[g.index("-r") + 1], "SID")
        self.assertNotIn("-c", g)


class ParseProbeTests(unittest.TestCase):
    """Defensive scraping of observed-only TUI usage text."""

    def test_parse_grok_like_output(self):
        text = ("some ui chrome\nWeekly limit: 18%\n"
                "Session (5h) limit: 40.5% used\n"
                "Next reset: July 13, 11:33 PT\n")
        r = tc.parse_probe_text(text)
        self.assertEqual(r["windows"]["weekly"]["used_percent"], 18.0)
        self.assertEqual(r["windows"]["5h"]["used_percent"], 40.5)
        self.assertTrue(any("July 13" in n for n in r["reset_notes"]))

    def test_parse_ignores_unrelated_percentages_and_garbage(self):
        self.assertEqual(tc.parse_probe_text("")["windows"], {})
        self.assertEqual(tc.parse_probe_text("progress: 50%")["windows"], {})
        r = tc.parse_probe_text("token usage garbage\n7-day limit: 73%\n")
        self.assertEqual(r["windows"]["weekly"]["used_percent"], 73.0)

    def test_parse_codex_like_percent_left_is_inverted(self):
        # codex /status phrases windows as remaining, e.g. "27% left"
        # (live-verified: complementary to its session-log used_percent)
        text = "5h limit: 100% left\nWeekly limit: 27% left (resets 00:41)\n"
        r = tc.parse_probe_text(text)
        self.assertEqual(r["windows"]["5h"]["used_percent"], 0.0)
        self.assertEqual(r["windows"]["weekly"]["used_percent"], 73.0)


class ProbeRunTests(unittest.TestCase):
    """`usage --probe` orchestration with the probe itself stubbed out."""

    def setUp(self):
        import tempfile
        self.tmpdir = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmpdir.name)
        os.environ["TEAMCTL_STATE"] = str(self.dir / "state.json")
        self._probes = tc.PROBES
        self._probe = tc.probe_provider
        self._which = tc.shutil.which
        tc.PROBES = {"fakeprov": {"argv": ["fakeprov"], "command": "/usage"}}
        tc.shutil.which = lambda name, *a, **k: (
            "/fake/bin/fakeprov" if name == "fakeprov" else None)

    def tearDown(self):
        tc.PROBES = self._probes
        tc.probe_provider = self._probe
        tc.shutil.which = self._which
        os.environ.pop("TEAMCTL_STATE", None)
        self.tmpdir.cleanup()

    def _usage(self, *extra):
        import contextlib
        import io
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = tc.main(["usage", *extra])
        return rc, out.getvalue(), err.getvalue()

    def test_probe_all_saves_and_reports_with_freshness(self):
        tc.probe_provider = lambda prov, spec, timeout=40.0: (
            {"windows": {"weekly": {"used_percent": 18.0}},
             "reset_notes": ["Next reset: July 13, 11:33 PT"]}, "")
        rc, out, _ = self._usage("--probe")
        self.assertEqual(rc, 0)
        self.assertIn("probing fakeprov", out)
        self.assertIn("probe ok — weekly 18%", out)
        self.assertIn("weekly: 18% used", out)              # reported below
        self.assertIn("July 13", out)
        cache = json.loads((self.dir / "probe-usage.json").read_text())
        self.assertEqual(cache["fakeprov"]["source"], "probe")
        self.assertEqual(
            cache["fakeprov"]["windows"]["weekly"]["used_percent"], 18.0)

    def test_probe_failure_degrades(self):
        tc.probe_provider = lambda prov, spec, timeout=40.0: (
            None, "the TUI never settled")
        rc, out, _ = self._usage("--probe", "fakeprov")
        self.assertEqual(rc, 0)
        self.assertIn("probe failed (the TUI never settled)", out)
        self.assertFalse((self.dir / "probe-usage.json").exists())

    def test_probe_claude_is_skipped_with_pointer(self):
        rc, out, _ = self._usage("--probe", "claude")
        self.assertEqual(rc, 0)
        self.assertIn("statusline cache", out)

    def test_probe_unknown_provider_rejected(self):
        rc, _, err = self._usage("--probe", "nope")
        self.assertEqual(rc, 2)
        self.assertIn("no probe defined", err)

    def test_stale_probe_data_flagged(self):
        import time as _t
        (self.dir / "probe-usage.json").write_text(json.dumps({
            "fakeprov": {"captured_at": _t.time() - 7200, "source": "probe",
                         "windows": {"weekly": {"used_percent": 9}},
                         "reset_notes": []}}))
        rc, out, _ = self._usage()
        self.assertEqual(rc, 0)
        self.assertIn("stale, consider `teamctl usage --probe`", out)


@unittest.skipUnless(os.environ.get("TMUX"), "requires a live tmux session")
class LiveProbeTests(unittest.TestCase):
    """A real hidden probe against a scripted fake TUI in the detached
    teamctl-probe session — settle-wait, capture-parse, verified teardown."""

    def setUp(self):
        import tempfile
        self.tmpdir = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmpdir.name)
        os.environ["TEAMCTL_STATE"] = str(self.dir / "state.json")
        self.tui = self.dir / "fake-tui.sh"
        self.tui.write_text(
            '#!/bin/bash\n'
            'echo "FakeTUI ready"\n'
            'while IFS= read -r line; do\n'
            '  if [ "$line" = "/usage" ]; then\n'
            '    echo "Weekly limit: 18% used"\n'
            '    echo "5h limit: 3% used"\n'
            '    echo "Next reset: July 13, 11:33 PT"\n'
            '  fi\n'
            'done\n')
        self.tui.chmod(0o755)

    def tearDown(self):
        tc.tmux("kill-session", "-t", f"={tc.PROBE_SESSION}", check=False)
        os.environ.pop("TEAMCTL_STATE", None)
        self.tmpdir.cleanup()

    def test_probe_roundtrip_and_verified_teardown(self):
        spec = {"argv": ["/bin/bash", str(self.tui)],
                "command": "/usage", "extra_enters": 1}
        result, err = tc.probe_provider("fake", spec, timeout=30.0)
        self.assertEqual(err, "")
        self.assertEqual(result["windows"]["weekly"]["used_percent"], 18.0)
        self.assertEqual(result["windows"]["5h"]["used_percent"], 3.0)
        self.assertTrue(any("July 13" in n for n in result["reset_notes"]))
        # the hidden session died with its only window — verified teardown
        self.assertFalse(tc._probe_session_exists())

    def test_probe_failure_when_tui_dies_instantly(self):
        spec = {"argv": ["/bin/bash", "-c", "exit 0"], "command": "/usage"}
        result, err = tc.probe_provider("fake", spec, timeout=8.0)
        self.assertIsNone(result)
        self.assertTrue(err)
        self.assertFalse(tc._probe_session_exists())


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
        rc, out = self._run_init(["opus", "high", "terse", "", "n", "n"])
        self.assertEqual(rc, 0)
        cfg = self._config()
        self.assertEqual(cfg["providers"]["claude"]["model"], "opus")
        self.assertEqual(cfg["providers"]["claude"]["effort"], "high")
        self.assertEqual(cfg["output"]["verbosity"], "terse")
        self.assertIn("revert", out)

    def test_rerun_backs_up_previous_config(self):
        rc, _ = self._run_init(["opus", "high", "normal", "", "n", "n"])
        self.assertEqual(rc, 0)
        rc, _ = self._run_init(["sonnet", "", "normal", "", "n", "n"])
        self.assertEqual(rc, 0)
        self.assertEqual(self._config()["providers"]["claude"]["model"], "sonnet")
        bak = self.home / ".config" / "agent-team" / "config.toml.bak-teamctl"
        self.assertTrue(bak.exists())
        self.assertIn('model = "opus"', bak.read_text())

    def test_tmux_block_appended_once_and_backed_up(self):
        conf = self.home / ".tmux.conf"
        conf.write_text("set -g mouse on\n")
        rc, _ = self._run_init(["", "", "", "", "y", "n"])
        self.assertEqual(rc, 0)
        text = conf.read_text()
        self.assertEqual(text.count(tc.TMUX_MARKER_BEGIN), 1)
        self.assertEqual(text.count(tc.TMUX_MARKER_END), 1)
        self.assertIn("set -g mouse on", text)          # original preserved
        self.assertIn("pane-border-format", text)
        self.assertTrue((self.home / ".tmux.conf.bak-teamctl").exists())
        # second accept must not duplicate the block
        rc, out = self._run_init(["", "", "", "", "y", "n"])
        self.assertEqual(rc, 0)
        self.assertEqual(conf.read_text().count(tc.TMUX_MARKER_BEGIN), 1)
        self.assertIn("skipping", out)

    def test_statusline_settings_added_minimally_and_skipped_if_present(self):
        settings = self.home / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({"model": "opus"}, indent=2))
        rc, _ = self._run_init(["", "", "", "", "n", "y"])
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
        rc, out = self._run_init(["", "", "", "", "n", "y"])
        self.assertEqual(rc, 0)
        self.assertEqual(settings.read_text(), before)
        self.assertIn("already has a statusLine key", out)

    def test_statusline_creates_settings_when_absent(self):
        rc, _ = self._run_init(["", "", "", "", "n", "y"])
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
    """Every live test runs in a dedicated throwaway tmux WINDOW: teamctl
    treats the window's own first pane as the lead (via TMUX_PANE). This
    keeps test panes out of the user's real window and gives them a
    predictably roomy layout — in a crowded real window, test panes came up
    tiny and wrapped output made pane-content assertions flaky."""

    def setUp(self):
        self.tmp = HERE / ".test-live-state.json"
        os.environ["TEAMCTL_STATE"] = str(self.tmp)
        self.tmp.unlink(missing_ok=True)
        out = tc.tmux("new-window", "-d", "-n", "teamctl-tests",
                      "-P", "-F", "#{window_id} #{pane_id}").stdout.split()
        self.window_id, self.lead_pane = out[0], out[1]
        # as generous a canvas as the tmux build allows (no-op pre-2.9)
        tc.tmux("resize-window", "-t", self.window_id, "-x", "220", "-y", "50",
                check=False)
        self._tmux_pane = os.environ.get("TMUX_PANE")
        os.environ["TMUX_PANE"] = self.lead_pane

    def tearDown(self):
        # best-effort cleanup of any pane we left behind
        for role in ("t_alpha", "t_beta", "rt_mate", "orphan_mate", "kill_mate"):
            tc.main(["shutdown", role])
        tc.tmux("kill-window", "-t", self.window_id, check=False)
        if self._tmux_pane is None:
            os.environ.pop("TMUX_PANE", None)
        else:
            os.environ["TMUX_PANE"] = self._tmux_pane
        self.tmp.unlink(missing_ok=True)
        Path(str(self.tmp) + ".tmp").unlink(missing_ok=True)
        os.environ.pop("TEAMCTL_STATE", None)

    def _active_pane(self) -> str:
        # the ACTIVE pane of the throwaway window (display-message with no -t
        # would resolve to the invoking pane, not the active one)
        out = tc.tmux("list-panes", "-t", self.window_id,
                      "-F", "#{pane_id} #{pane_active}").stdout
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

    def test_lead_width_pinned_and_foreign_pane_folded(self):
        original = tc.load_config
        tc.load_config = lambda: {"layout": {"lead_width": 40}}
        try:
            # a foreign (non-teamctl) pane already occupies the right side
            tc.tmux("split-window", "-h", "-d", "-P", "-F", "#{pane_id}",
                    "-t", self.lead_pane)
            # the lead is never a split candidate; the foreign pane is
            self.assertNotIn(self.lead_pane,
                             tc._split_candidates(self.lead_pane, []))
            self.assertEqual(
                tc.main(["spawn", "t_alpha", "--provider", "shell"]), 0)
            # teammate folded in beside the foreign pane, lead not re-split
            self.assertEqual(len(tc._window_panes(self.lead_pane)), 3)
            win_w = int(tc.tmux("display-message", "-p", "-t", self.window_id,
                                "#{window_width}").stdout.strip())
            lead_w, _ = tc._pane_size(self.lead_pane)
            self.assertLessEqual(abs(lead_w - int(win_w * 0.40)), 3,
                                 f"lead {lead_w} not ~40% of {win_w}")
            # shutdown re-pins the lead width too
            self.assertEqual(tc.main(["shutdown", "t_alpha"]), 0)
            lead_w2, _ = tc._pane_size(self.lead_pane)
            self.assertLessEqual(abs(lead_w2 - int(win_w * 0.40)), 3)
        finally:
            tc.load_config = original

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
