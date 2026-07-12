"""v0.5.0 provider-spec registry tests: gemini (the 4th provider) and the
[providers.custom.*] escape hatch.

Gemini's argv shapes were VERIFIED against a live gemini-cli 0.46.0 install
(2026-07-12): `-p` headless, `--output-format json`, `-m` model, NO effort
flag, `--resume <uuid>` (prompt must ride -p), and a `session_id` field in
the JSON output — present on success AND error output, with error JSON
landing on stderr.

Run with:  python3 -m unittest tests.test_providers_registry
"""

import contextlib
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEAMCTL = HERE.parent / "teamctl"

loader = SourceFileLoader("teamctl_registry", str(TEAMCTL))
spec = importlib.util.spec_from_loader("teamctl_registry", loader)
tc = importlib.util.module_from_spec(spec)
loader.exec_module(tc)

TASK = "summarize the failures"
SID = "0a1b2c3d-4e5f-6789-abcd-ef0123456789"


class _SandboxHome(unittest.TestCase):
    """Fresh HOME + state dir + pinned which + provider env keys stripped."""

    INSTALLED: tuple = ()

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.home = Path(self.tmpdir.name)
        self._home_env = os.environ.get("HOME")
        os.environ["HOME"] = str(self.home)
        os.environ["TEAMCTL_STATE"] = str(self.home / "state.json")
        os.environ["TEAMCTL_NO_KEYCHAIN"] = "1"
        self._saved_env = {}
        for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "XAI_API_KEY",
                    "GEMINI_API_KEY", "GOOGLE_API_KEY",
                    "GOOGLE_APPLICATION_CREDENTIALS"):
            self._saved_env[var] = os.environ.pop(var, None)
        self.installed = set(self.INSTALLED)
        self._which = tc.shutil.which
        tc.shutil.which = lambda name, *a, **k: (
            f"/fake/bin/{name}" if name in self.installed else None)

    def tearDown(self):
        tc.shutil.which = self._which
        for var, val in self._saved_env.items():
            if val is not None:
                os.environ[var] = val
        os.environ.pop("TEAMCTL_NO_KEYCHAIN", None)
        os.environ.pop("TEAMCTL_STATE", None)
        if self._home_env is not None:
            os.environ["HOME"] = self._home_env
        self.tmpdir.cleanup()

    def write_config(self, text: str) -> None:
        cfg = self.home / ".config" / "agent-team"
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "config.toml").write_text(text)

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = tc.main(list(argv))
        return rc, out.getvalue(), err.getvalue()


class GeminiAdapterGoldens(unittest.TestCase):
    """The exact argv teamctl emits for gemini — pinned like the other
    providers' goldens in test_adapter_goldens."""

    def test_headless_argv(self):
        self.assertEqual(
            tc.headless_argv("gemini", TASK, "", ""),
            ["gemini", "-p", TASK, "--output-format", "json"])
        self.assertEqual(
            tc.headless_argv("gemini", TASK, "gemini-2.5-pro", ""),
            ["gemini", "-p", TASK, "--output-format", "json",
             "-m", "gemini-2.5-pro"])

    def test_resume_argv_is_exact_uuid(self):
        # --resume takes "latest"/index too — teamctl must ONLY ever emit
        # the captured uuid (exact-session rule), with the prompt on -p
        # (the only prompt channel that works with --resume, issue #14180)
        a = tc.resume_argv("gemini", TASK, "", "", SID)
        self.assertEqual(a, ["gemini", "--resume", SID, "-p", TASK,
                             "--output-format", "json"])
        self.assertNotIn("latest", a)
        b = tc.resume_argv("gemini", TASK, "gemini-2.5-pro", "high", SID)
        self.assertEqual(b, ["gemini", "--resume", SID, "-p", TASK,
                             "--output-format", "json",
                             "-m", "gemini-2.5-pro"])   # effort never resent

    def test_effort_is_dropped_with_a_note_never_silently(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            a = tc.headless_argv("gemini", TASK, "", "high")
        self.assertEqual(a, ["gemini", "-p", TASK, "--output-format", "json"])
        self.assertIn("gemini has no effort flag", err.getvalue())
        self.assertIn("--effort ignored", err.getvalue())

    def test_interactive_flags(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            f = tc.interactive_flags("gemini", "gemini-2.5-flash", "low")
        self.assertEqual(f, ["-m", "gemini-2.5-flash"])
        self.assertIn("no effort flag", err.getvalue())

    def test_gemini_is_routable_and_spawnable(self):
        self.assertIn("gemini", tc.routable_providers())
        self.assertIn("gemini", tc.PROVIDERS)
        self.assertEqual(tc.PROVIDERS["gemini"], ["gemini"])


class GeminiSessionCaptureTests(unittest.TestCase):
    """session_id capture from gemini's JSON artifacts — including the
    live-verified error shape (error JSON lands on STDERR → error.log)."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.hd = Path(self.tmpdir.name) / "mate"
        self.hd.mkdir()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_top_level_session_id_in_result_json(self):
        (self.hd / "result.json").write_text(json.dumps(
            {"session_id": SID, "response": "hi",
             "stats": {"total_tokens": 12}}))
        self.assertEqual(tc._extract_session_id("gemini", self.hd), SID)

    def test_nested_session_id_found_recursively(self):
        (self.hd / "result.json").write_text(json.dumps(
            {"meta": {"session_id": SID}, "response": "hi"}))
        self.assertEqual(tc._extract_session_id("gemini", self.hd), SID)

    def test_error_json_on_stderr_still_yields_the_id(self):
        # the exact live-captured 0.46.0 error shape: stdout empty, the
        # error JSON (session_id included) on stderr
        (self.hd / "result.json").write_text("")
        (self.hd / "error.log").write_text(json.dumps(
            {"session_id": SID,
             "error": {"type": "Error", "message": "Please set an Auth "
                       "method", "code": 41}}))
        self.assertEqual(tc._extract_session_id("gemini", self.hd), SID)

    def test_garbage_artifacts_yield_none(self):
        (self.hd / "result.json").write_text("{broken")
        (self.hd / "error.log").write_text("plain stderr text, no json")
        self.assertIsNone(tc._extract_session_id("gemini", self.hd))


class GeminiFollowupTests(unittest.TestCase):
    """followup with gemini: exact captured session or refusal."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmpdir.name)
        os.environ["TEAMCTL_STATE"] = str(self.dir / "state.json")
        self._home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.dir)
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
        if self._home is not None:
            os.environ["HOME"] = self._home
        os.environ.pop("TEAMCTL_STATE", None)
        self.tmpdir.cleanup()

    def _seed(self, provider="gemini", session=None, cwd=None):
        hd = self.dir / "mate"
        hd.mkdir(exist_ok=True)
        if session:
            (hd / "session").write_text(session + "\n")
        tc.save_state({"teammates": {"mate": {
            "provider": provider, "pane_id": "%1",
            "cwd": cwd or str(self.dir), "model": "", "effort": "",
            "mode": "dispatch", "handoff": str(hd),
            "created_at": "2026-01-01T00:00:00"}}})
        return hd

    def _followup(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = tc.main(["followup", "mate", "--task", "next"])
        return rc, out.getvalue(), err.getvalue()

    def test_followup_resumes_exact_uuid(self):
        self._seed(session=SID)
        rc, _, _ = self._followup()
        self.assertEqual(rc, 0)
        argv = self.argv_seen[0]
        self.assertEqual(argv[argv.index("--resume") + 1], SID)
        self.assertNotIn("latest", argv)

    def test_followup_refuses_without_captured_id(self):
        self._seed(session=None)
        rc, _, err = self._followup()
        self.assertEqual(rc, 1)
        self.assertIn("no session id captured", err)
        self.assertIn("never guesses", err)
        self.assertEqual(self.argv_seen, [])

    def test_followup_reuses_dispatch_cwd(self):
        # gemini sessions are PROJECT-SCOPED (keyed to the cwd): the
        # follow-up must run where the dispatch ran or the uuid cannot
        # resolve. cmd_followup reuses info["cwd"] — pin that here.
        workdir = self.dir / "project"
        workdir.mkdir()
        self._seed(session=SID, cwd=str(workdir))
        seen = {}
        tc._dispatch_pane = (lambda role, hd, argv, cwd, provider, model:
                             seen.setdefault("cwd", cwd) or "%fake")
        rc, _, _ = self._followup()
        self.assertEqual(rc, 0)
        self.assertEqual(seen["cwd"], str(workdir))


class GeminiAuthLatticeTests(_SandboxHome):
    """gemini in the auth lattice: oauth_creds.json + env keys, honest
    unknown on corruption, and 'quiet' forever (no usage source)."""

    def test_oauth_creds_mean_signed_in(self):
        d = self.home / ".gemini"
        d.mkdir()
        (d / "oauth_creds.json").write_text(json.dumps(
            {"access_token": "t", "refresh_token": "r"}))
        self.assertEqual(tc.provider_auth_state("gemini")[0], "signed-in")

    def test_missing_creds_mean_signed_out(self):
        self.assertEqual(tc.provider_auth_state("gemini")[0], "signed-out")
        # an empty dict holds no credentials either
        d = self.home / ".gemini"
        d.mkdir()
        (d / "oauth_creds.json").write_text("{}")
        self.assertEqual(tc.provider_auth_state("gemini")[0], "signed-out")

    def test_corrupt_creds_are_unknown_not_a_guess(self):
        d = self.home / ".gemini"
        d.mkdir()
        (d / "oauth_creds.json").write_text("{not json")
        state, note = tc.provider_auth_state("gemini")
        self.assertEqual(state, "unknown")
        self.assertIn("unreadable", note)

    def test_env_keys_count_as_signed_in(self):
        for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
            os.environ[var] = "k"
            try:
                state, note = tc.provider_auth_state("gemini")
                self.assertEqual(state, "signed-in", var)
                self.assertIn("exported API key", note)
            finally:
                os.environ.pop(var)

    def test_lattice_states_render(self):
        # not installed
        self.assertEqual(tc.provider_state("gemini")[0], "not installed")
        # locked out
        self.installed.add("gemini")
        self.assertEqual(tc.provider_state("gemini")[0], "locked out")
        # quiet (signed in; gemini has no usage source, so never 'ready'
        # without a probe cache — and it ships with no probe)
        d = self.home / ".gemini"
        d.mkdir()
        (d / "oauth_creds.json").write_text(json.dumps({"access_token": "t"}))
        self.assertEqual(tc.provider_state("gemini")[0], "quiet")

    def test_providers_table_and_usage_show_gemini(self):
        self.installed.add("gemini")
        d = self.home / ".gemini"
        d.mkdir()
        (d / "oauth_creds.json").write_text(json.dumps({"access_token": "t"}))
        rc, out, _ = self.run_cli("providers")
        self.assertEqual(rc, 0)
        self.assertIn("gemini", out)
        self.assertIn("no local usage feed", out)       # the honest hint
        rc, out, _ = self.run_cli("usage", "--json")
        data = json.loads(out)
        self.assertIn("gemini", data)                   # a first-class key
        self.assertIsNone(data["gemini"])               # with no fake data
        self.assertEqual(data["states"]["gemini"]["state"], "quiet")

    def test_no_probe_defined_for_gemini(self):
        rc, _, err = self.run_cli("usage", "--probe", "gemini")
        self.assertEqual(rc, 2)
        self.assertIn("no probe defined", err)


class ClassifySignalTests(unittest.TestCase):
    def test_gemini_signals_classify(self):
        # RESOURCE_EXHAUSTED is the Gemini API quota status; the auth line
        # is the live-captured 0.46.0 headless message
        self.assertEqual(tc.classify_output(
            "Error: 429 RESOURCE_EXHAUSTED: Quota exceeded"), "exhausted")
        self.assertEqual(tc.classify_output(
            "Please set an Auth method in your settings.json"), "auth-error")


CUSTOM_BLOCK = """
[providers.custom.aider]
command = "aider"
headless_args = ["--message", "{task}", "--yes"]
model_args = ["--model", "{model}"]
effort_args = []
resume_args = []
interactive_args = ["--no-auto-commits"]
login_hint = "aider --login"
routable = true
"""


class CustomProviderTests(_SandboxHome):
    """[providers.custom.*]: the same substrate gemini is defined through,
    exposed to users — with honest degrades at every missing capability."""

    INSTALLED = ("aider",)

    def test_valid_block_round_trip(self):
        self.write_config(CUSTOM_BLOCK)
        spec = tc.provider_spec("aider")
        self.assertIsNotNone(spec)
        self.assertTrue(spec["custom"])
        self.assertIn("aider", tc.routable_providers())
        self.assertIn("aider", tc.known_provider_names())
        self.assertEqual(
            tc.headless_argv("aider", TASK, "", ""),
            ["aider", "--message", TASK, "--yes"])
        self.assertEqual(
            tc.headless_argv("aider", TASK, "gpt-x", ""),
            ["aider", "--message", TASK, "--yes", "--model", "gpt-x"])

    def test_interactive_spawn_dry_run(self):
        self.write_config(CUSTOM_BLOCK)
        rc, out, _ = self.run_cli("spawn", "helper", "--provider", "aider",
                                  "--prompt", "hello", "--dry-run")
        self.assertEqual(rc, 0)
        self.assertIn("aider --no-auto-commits hello", out)

    def test_effort_dropped_with_note(self):
        self.write_config(CUSTOM_BLOCK)           # effort_args = []
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            a = tc.headless_argv("aider", TASK, "", "high")
        self.assertNotIn("high", a)
        self.assertIn("aider has no effort flag", err.getvalue())

    def test_followup_refused_when_no_resume(self):
        self.write_config(CUSTOM_BLOCK)           # resume_args = []
        with self.assertRaises(tc.TeamctlError):
            tc.resume_argv("aider", TASK, "", "", SID)
        # end-to-end: a dispatched aider mate cannot follow up
        hd = self.home / "mate"
        hd.mkdir()
        tc.save_state({"teammates": {"mate": {
            "provider": "aider", "pane_id": "", "cwd": str(self.home),
            "model": "", "effort": "", "mode": "dispatch",
            "handoff": str(hd), "created_at": "2026-01-01T00:00:00"}}})
        saved_tmux = os.environ.get("TMUX")
        os.environ["TMUX"] = "/fake/sock,1,0"
        saved_reconcile = tc.reconcile
        tc.reconcile = lambda state: state
        try:
            rc, _, err = self.run_cli("followup", "mate", "--task", "next")
        finally:
            tc.reconcile = saved_reconcile
            if saved_tmux is None:
                os.environ.pop("TMUX", None)
            else:
                os.environ["TMUX"] = saved_tmux
        self.assertEqual(rc, 1)
        self.assertIn("cannot resume", err)
        self.assertIn("Re-dispatch instead", err)

    def test_resume_with_session_key_works(self):
        self.write_config("""
[providers.custom.mycli]
command = "mycli"
headless_args = ["run", "{task}"]
resume_args = ["resume", "{session_id}", "{task}"]
session_id_key = "sid"
""")
        self.assertEqual(
            tc.resume_argv("mycli", TASK, "", "", "S-1"),
            ["mycli", "resume", "S-1", TASK])
        hd = self.home / "m2"
        hd.mkdir()
        (hd / "result.json").write_text(json.dumps({"sid": "S-1"}))
        self.assertEqual(tc._extract_session_id("mycli", hd), "S-1")

    def test_stderr_regex_session_source(self):
        self.write_config("""
[providers.custom.regexcli]
command = "regexcli"
headless_args = ["{task}"]
resume_args = ["--resume", "{session_id}", "{task}"]
session_id_regex = "session:\\\\s*(\\\\S+)"
""")
        hd = self.home / "m3"
        hd.mkdir()
        (hd / "error.log").write_text("starting up\nsession: tok_99\n")
        self.assertEqual(tc._extract_session_id("regexcli", hd), "tok_99")

    def test_unprobed_auth_is_stated_and_routable(self):
        self.write_config(CUSTOM_BLOCK)
        state, note = tc.provider_auth_state("aider")
        self.assertEqual(state, "unprobed")
        self.assertIn("auth not probed", note)
        # lattice: quiet with the caveat, and route keeps it (D9)
        self.assertEqual(tc.provider_state("aider")[0], "quiet")
        rc, out, _ = self.run_cli("providers")
        self.assertIn("auth not probed", out)
        selected, _, exclusions, _ranking = tc.route_select(["aider"])
        self.assertEqual(selected, "aider")
        self.assertEqual(exclusions, {})

    def test_auth_files_enable_the_full_lattice(self):
        self.write_config(CUSTOM_BLOCK + '\nauth_files = ["~/.aider/auth.json"]\n')
        self.assertEqual(tc.provider_auth_state("aider")[0], "signed-out")
        d = self.home / ".aider"
        d.mkdir()
        (d / "auth.json").write_text(json.dumps({"token": "t"}))
        self.assertEqual(tc.provider_auth_state("aider")[0], "signed-in")

    def test_probe_command_joins_probe_specs(self):
        self.write_config(CUSTOM_BLOCK + '\nprobe_command = "/usage"\n')
        probes = tc.probe_specs()
        self.assertIn("aider", probes)
        self.assertEqual(probes["aider"]["command"], "/usage")
        self.assertEqual(probes["aider"]["argv"], ["aider"])

    def test_routable_false_excluded_from_tables(self):
        self.write_config(CUSTOM_BLOCK.replace("routable = true",
                                               "routable = false"))
        self.assertNotIn("aider", tc.routable_providers())
        # ... but still spawnable by name
        self.assertIsNotNone(tc.provider_spec("aider"))


class CustomProviderValidationTests(_SandboxHome):
    """Malformed blocks are skipped with one honest warning — and can
    never take the built-ins down. Unique names per test: warnings are
    deliberately once-per-process."""

    def _specs_and_warning(self, toml_text):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            specs = tc.custom_provider_specs()
        return specs, err.getvalue()

    def test_missing_task_placeholder_is_skipped(self):
        self.write_config("""
[providers.custom.badtask]
command = "badtask"
headless_args = ["--go"]
""")
        specs, warning = self._specs_and_warning("")
        self.assertNotIn("badtask", specs)
        self.assertIn("{task}", warning)
        # built-ins unaffected
        self.assertIn("claude", tc.routable_providers())

    def test_shadowing_a_builtin_is_refused(self):
        self.write_config("""
[providers.custom.claude]
command = "evil-claude"
headless_args = ["{task}"]
""")
        specs, warning = self._specs_and_warning("")
        self.assertNotIn("claude", specs)
        self.assertIn("shadows a built-in", warning)
        self.assertEqual(tc.provider_spec("claude")["argv"], ["claude"])

    def test_reserved_words_are_refused(self):
        self.write_config("""
[providers.custom.all]
command = "allcli"
headless_args = ["{task}"]
""")
        specs, _ = self._specs_and_warning("")
        self.assertNotIn("all", specs)

    def test_bad_name_shape_is_refused(self):
        self.write_config("""
[providers.custom."-dash"]
command = "dashcli"
headless_args = ["{task}"]
""")
        specs, warning = self._specs_and_warning("")
        self.assertEqual(specs, {})
        self.assertIn("provider names", warning)

    def test_non_list_args_are_refused(self):
        self.write_config("""
[providers.custom.badlist]
command = "badlist"
headless_args = "not-a-list {task}"
""")
        specs, warning = self._specs_and_warning("")
        self.assertNotIn("badlist", specs)
        self.assertIn("lists of strings", warning)

    def test_missing_command_is_refused(self):
        self.write_config("""
[providers.custom.nocmd]
headless_args = ["{task}"]
""")
        specs, warning = self._specs_and_warning("")
        self.assertNotIn("nocmd", specs)
        self.assertIn("command", warning)

    def test_resume_without_session_source_degrades_to_no_followups(self):
        self.write_config("""
[providers.custom.noresume]
command = "noresume"
headless_args = ["{task}"]
resume_args = ["--continue", "{session_id}"]
""")
        specs, warning = self._specs_and_warning("")
        self.assertIn("noresume", specs)                # block survives
        self.assertIsNone(specs["noresume"]["resume"])  # capability doesn't
        self.assertIn("follow-ups disabled", warning)

    def test_spawn_only_provider_refuses_dispatch(self):
        self.write_config("""
[providers.custom.spawnonly]
command = "spawnonly"
interactive_args = ["--chat"]
""")
        self.assertIsNotNone(tc.provider_spec("spawnonly"))
        with self.assertRaises(tc.TeamctlError):
            tc.headless_argv("spawnonly", TASK, "", "")

    def test_unknown_provider_error_lists_known_names(self):
        rc, _, err = self.run_cli("spawn", "r", "--provider", "nonesuch",
                                  "--dry-run")
        self.assertEqual(rc, 2)
        self.assertIn("unknown provider", err)
        self.assertIn("gemini", err)


@unittest.skipUnless(
    os.environ.get("TMUX") and shutil.which("gemini"),
    "requires a live tmux session and an installed gemini CLI")
class LiveGeminiTests(unittest.TestCase):
    """The §1.8 checklist as a test: one real dispatch → session_id
    captured → one exact-session followup. Skips (honestly) unless gemini
    is signed in — sign in with `gemini` + /auth, or GEMINI_API_KEY."""

    def setUp(self):
        if not tc.provider_authed("gemini"):
            self.skipTest("gemini is installed but not signed in")
        self.statedir = tempfile.TemporaryDirectory(prefix="teamctl-gem-")
        self.tmp = Path(self.statedir.name) / "state.json"
        os.environ["TEAMCTL_STATE"] = str(self.tmp)
        out = tc.tmux("new-window", "-d", "-n", f"teamctl-gem-{os.getpid()}",
                      "-P", "-F", "#{window_id} #{pane_id}").stdout.split()
        self.window_id, self.lead_pane = out[0], out[1]
        self._tmux_pane = os.environ.get("TMUX_PANE")
        os.environ["TMUX_PANE"] = self.lead_pane

    def tearDown(self):
        for role in list(tc.load_state()["teammates"]):
            tc.main(["shutdown", role])
        tc.tmux("kill-window", "-t", self.window_id, check=False)
        if self._tmux_pane is None:
            os.environ.pop("TMUX_PANE", None)
        else:
            os.environ["TMUX_PANE"] = self._tmux_pane
        os.environ.pop("TEAMCTL_STATE", None)
        self.statedir.cleanup()

    def test_dispatch_capture_followup_roundtrip(self):
        rc = tc.main(["dispatch", "gem_live", "--provider", "gemini",
                      "--task", "Reply with exactly the word: teal",
                      "--cwd", self.statedir.name])
        self.assertEqual(rc, 0)
        rc = tc.main(["result", "gem_live", "--wait", "--timeout", "180"])
        self.assertEqual(rc, 0, "gemini dispatch failed — see error.log")
        info = tc.load_state()["teammates"]["gem_live"]
        hd = Path(info["handoff"])
        sid = tc._capture_session_id(info, hd)
        self.assertTrue(sid, "no session_id captured from gemini JSON")
        self.assertRegex(sid, r"^[0-9a-fA-F-]{36}$")
        # exact-session followup, same cwd (project-scoped sessions)
        rc = tc.main(["followup", "gem_live",
                      "--task", "Repeat the word from my last message."])
        self.assertEqual(rc, 0)
        rc = tc.main(["result", "gem_live", "--wait", "--timeout", "180"])
        self.assertEqual(rc, 0, "gemini exact-session resume failed "
                                "(known flaky upstream: issue #24808)")
        result = json.loads((hd / "result.json").read_text())
        self.assertIn("teal", json.dumps(result).lower())


if __name__ == "__main__":
    unittest.main()
