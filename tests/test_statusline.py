"""Tests for the claude-statusline rate-limit cache and `teamctl usage`'s
Claude reporting.

The statusline is exercised as a real subprocess against a throwaway HOME;
the usage command reads its cache from the (TEAMCTL_STATE-overridden) state
dir. Nothing here touches the real ~/.local/state or ~/.claude.

Run with:  python3 -m unittest discover -s tests
"""

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATUSLINE = HERE.parent / "claude-statusline"
TEAMCTL = HERE.parent / "teamctl"

loader = SourceFileLoader("teamctl", str(TEAMCTL))
spec = importlib.util.spec_from_loader("teamctl", loader)
tc = importlib.util.module_from_spec(spec)
loader.exec_module(tc)

FULL_PAYLOAD = {
    "model": {"display_name": "Opus"},
    "effort": {"level": "high"},
    "context_window": {"used_percentage": 8},
    "rate_limits": {
        "five_hour": {"used_percentage": 23.5, "resets_at": 1738425600},
        "seven_day": {"used_percentage": 41.2, "resets_at": 1738857600},
    },
}


class StatuslineTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.home = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def run_sl(self, payload: str):
        env = dict(os.environ)
        env["HOME"] = str(self.home)
        return subprocess.run([sys.executable, str(STATUSLINE)],
                              input=payload, capture_output=True,
                              text=True, env=env, timeout=30)

    @property
    def cache(self) -> Path:
        return (self.home / ".local" / "state" / "agent-team"
                / "claude-usage.json")

    def test_prints_line_and_dumps_rate_limits(self):
        r = self.run_sl(json.dumps(FULL_PAYLOAD))
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "Opus · high · ctx 8%")
        data = json.loads(self.cache.read_text())
        rl = data["rate_limits"]
        self.assertEqual(rl["five_hour"]["used_percentage"], 23.5)
        self.assertEqual(rl["five_hour"]["resets_at"], 1738425600)
        self.assertEqual(rl["seven_day"]["used_percentage"], 41.2)
        self.assertAlmostEqual(data["captured_at"], time.time(), delta=60)

    def test_no_rate_limits_prints_but_writes_no_cache(self):
        payload = {k: v for k, v in FULL_PAYLOAD.items() if k != "rate_limits"}
        r = self.run_sl(json.dumps(payload))
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "Opus · high · ctx 8%")
        self.assertFalse(self.cache.exists())

    def test_partial_windows_cached_partially(self):
        payload = dict(FULL_PAYLOAD)
        payload["rate_limits"] = {
            "seven_day": {"used_percentage": 12, "resets_at": None}}
        r = self.run_sl(json.dumps(payload))
        self.assertEqual(r.returncode, 0)
        rl = json.loads(self.cache.read_text())["rate_limits"]
        self.assertNotIn("five_hour", rl)
        self.assertEqual(rl["seven_day"]["used_percentage"], 12)
        self.assertIsNone(rl["seven_day"]["resets_at"])

    def test_invalid_json_never_crashes(self):
        r = self.run_sl("this is not json")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "claude · ? · ?")
        self.assertFalse(self.cache.exists())

    def test_unwritable_state_dir_never_breaks_the_line(self):
        # ~/.local/state/agent-team exists as a FILE -> makedirs/open fail
        (self.home / ".local" / "state").mkdir(parents=True)
        (self.home / ".local" / "state" / "agent-team").write_text("a file")
        r = self.run_sl(json.dumps(FULL_PAYLOAD))
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "Opus · high · ctx 8%")


class UsageClaudeCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmpdir.name)
        os.environ["TEAMCTL_STATE"] = str(self.dir / "state.json")
        # pin the lattice inputs: claude installed and signed in, the other
        # CLIs absent — `usage` output must not depend on the host machine
        self._which = tc.shutil.which
        self._auth_state = tc.provider_auth_state
        tc.shutil.which = lambda name, *a, **k: (
            "/fake/bin/claude" if name == "claude" else None)
        tc.provider_auth_state = lambda p: (
            ("signed-in", "") if p == "claude" else ("signed-out", ""))

    def tearDown(self):
        tc.shutil.which = self._which
        tc.provider_auth_state = self._auth_state
        os.environ.pop("TEAMCTL_STATE", None)
        self.tmpdir.cleanup()

    def _write_cache(self, five_pct=None, seven_pct=None, resets_in=3600.0,
                     captured_ago=30.0):
        now = time.time()
        rl = {}
        if five_pct is not None:
            rl["five_hour"] = {"used_percentage": five_pct,
                               "resets_at": now + resets_in}
        if seven_pct is not None:
            rl["seven_day"] = {"used_percentage": seven_pct,
                               "resets_at": now + resets_in}
        (self.dir / "claude-usage.json").write_text(json.dumps(
            {"captured_at": now - captured_ago, "rate_limits": rl}))

    def _usage(self, *extra):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = tc.main(["usage", *extra])
        return rc, out.getvalue(), err.getvalue()

    def test_usage_json_reports_claude_windows(self):
        self._write_cache(five_pct=42, seven_pct=7)
        rc, out, _ = self._usage("--json")
        self.assertEqual(rc, 0)
        claude = json.loads(out)["claude"]
        self.assertEqual(claude["5h"]["used_percent"], 42)
        self.assertEqual(claude["weekly"]["used_percent"], 7)
        self.assertIn("captured_at", claude)

    def test_usage_text_labels_source_and_freshness(self):
        self._write_cache(five_pct=42, captured_ago=90)
        rc, out, _ = self._usage()
        self.assertEqual(rc, 0)
        self.assertIn("5h: 42% used", out)
        self.assertIn("statusline cache", out)
        self.assertIn("1m ago", out)

    def test_usage_text_no_data_message(self):
        # signed in with no usage data = quiet, with the wake hint
        rc, out, _ = self._usage()
        self.assertEqual(rc, 0)
        self.assertIn("quiet — signed in, no usage data yet", out)
        self.assertIn("statusline", out)

    def test_claude_exhaustion_records_routing_signal(self):
        self._write_cache(five_pct=100)
        rc, _, _ = self._usage("--json")
        self.assertEqual(rc, 0)
        signals = json.loads((self.dir / "providers.json").read_text())
        self.assertEqual(signals["claude"]["signal"], "exhausted")
        self.assertGreater(signals["claude"]["resets_at"], time.time())

    def test_corrupt_or_shapeless_cache_ignored(self):
        (self.dir / "claude-usage.json").write_text("{broken")
        rc, out, _ = self._usage("--json")
        self.assertEqual(rc, 0)
        self.assertIsNone(json.loads(out)["claude"])
        (self.dir / "claude-usage.json").write_text('{"rate_limits": "nope"}')
        rc, out, _ = self._usage("--json")
        self.assertEqual(rc, 0)
        self.assertIsNone(json.loads(out)["claude"])


if __name__ == "__main__":
    unittest.main()
