"""Adapter-argv GOLDEN tests — the provider-registry refactor's safety net.

Every argv below was snapshotted from the v0.4.0 adapter functions
(`headless_argv`, `resume_argv`, `interactive_flags`, `build_launch_line`)
BEFORE the v0.5.0 provider-spec registry replaced their bodies. The
registry refactor must reproduce these BYTE-IDENTICALLY: these tests are
the proof that "refactor" meant refactor.

New providers (gemini, custom) get their own goldens as they land, in the
same table style, so the exact CLI surface orchestrator emits is always pinned.

Run with:  python3 -m unittest tests.test_adapter_goldens
"""

import importlib.util
import os
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEAMCTL = HERE.parent / "orchestrator"

loader = SourceFileLoader("teamctl_goldens", str(TEAMCTL))
spec = importlib.util.spec_from_loader("teamctl_goldens", loader)
tc = importlib.util.module_from_spec(spec)
loader.exec_module(tc)

SH = os.environ.get("SHELL", "/bin/bash")

TASK = "review the diff; report risks"
SID = "0a1b2c3d-4e5f-6789-abcd-ef0123456789"


class HeadlessArgvGoldens(unittest.TestCase):
    """headless_argv(provider, task, model, effort) — exact v0.4.0 argv."""

    # (provider, model, effort) -> exact argv
    GOLDENS = {
        ("claude", "", ""): ["claude", "-p", TASK, "--output-format", "json"],
        ("claude", "opus", ""): ["claude", "-p", TASK, "--output-format",
                                 "json", "--model", "opus"],
        ("claude", "", "high"): ["claude", "-p", TASK, "--output-format",
                                 "json", "--effort", "high"],
        ("claude", "opus", "high"): ["claude", "-p", TASK, "--output-format",
                                     "json", "--model", "opus",
                                     "--effort", "high"],
        ("grok", "", ""): ["grok", "--single", TASK, "--output-format",
                           "json"],
        ("grok", "grok-4", "low"): ["grok", "--single", TASK,
                                    "--output-format", "json",
                                    "-m", "grok-4", "--effort", "low"],
        ("codex", "", ""): ["codex", "exec", TASK],
        ("codex", "gpt-5.2-codex", ""): ["codex", "exec", TASK,
                                         "-m", "gpt-5.2-codex"],
        ("codex", "", "xhigh"): ["codex", "exec", TASK,
                                 "-c", 'model_reasoning_effort="xhigh"'],
        ("codex", "gpt-5.2-codex", "xhigh"): [
            "codex", "exec", TASK, "-m", "gpt-5.2-codex",
            "-c", 'model_reasoning_effort="xhigh"'],
        # model/effort are silently ignored for the shell test provider
        ("shell", "", ""): [SH, "-c", TASK],
        ("shell", "m", "e"): [SH, "-c", TASK],
    }

    def test_headless_argv_matches_v040_exactly(self):
        for (prov, model, effort), want in self.GOLDENS.items():
            with self.subTest(provider=prov, model=model, effort=effort):
                self.assertEqual(
                    tc.headless_argv(prov, TASK, model, effort), want)

    def test_unknown_provider_still_refuses(self):
        with self.assertRaises(tc.TeamctlError):
            tc.headless_argv("nonesuch", TASK, "", "")


class ResumeArgvGoldens(unittest.TestCase):
    """resume_argv(provider, task, model, effort, session_id) — exact
    v0.4.0 argv. Notable pinned behaviors: codex takes NEITHER model nor
    effort on resume; claude and grok re-send the model but never the
    effort; every resume names the EXACT session id (never 'latest')."""

    GOLDENS = {
        ("claude", "", ""): ["claude", "-p", TASK, "--output-format", "json",
                             "--resume", SID],
        ("claude", "opus", "high"): ["claude", "-p", TASK, "--output-format",
                                     "json", "--resume", SID,
                                     "--model", "opus"],
        ("grok", "", ""): ["grok", "--single", TASK, "--output-format",
                           "json", "-r", SID],
        ("grok", "grok-4", "low"): ["grok", "--single", TASK,
                                    "--output-format", "json", "-r", SID,
                                    "-m", "grok-4"],
        ("codex", "", ""): ["codex", "exec", "resume", SID, TASK],
        ("codex", "gpt-5.2-codex", "xhigh"): ["codex", "exec", "resume",
                                              SID, TASK],
        ("shell", "", ""): [SH, "-c", TASK],
        ("shell", "m", "e"): [SH, "-c", TASK],
    }

    def test_resume_argv_matches_v040_exactly(self):
        for (prov, model, effort), want in self.GOLDENS.items():
            with self.subTest(provider=prov, model=model, effort=effort):
                self.assertEqual(
                    tc.resume_argv(prov, TASK, model, effort, SID), want)

    def test_session_id_always_present_for_ai_providers(self):
        # the exact-session rule, mechanically: the captured id must appear
        # verbatim in every AI provider's resume argv
        for prov in ("claude", "grok", "codex"):
            with self.subTest(provider=prov):
                self.assertIn(SID, tc.resume_argv(prov, TASK, "", "", SID))

    def test_unknown_provider_still_refuses(self):
        with self.assertRaises(tc.TeamctlError):
            tc.resume_argv("nonesuch", TASK, "", "", SID)


class InteractiveFlagsGoldens(unittest.TestCase):
    """interactive_flags(provider, model, effort) — exact v0.4.0 flags."""

    GOLDENS = {
        ("claude", "", ""): [],
        ("claude", "opus", ""): ["--model", "opus"],
        ("claude", "", "high"): ["--effort", "high"],
        ("claude", "opus", "high"): ["--model", "opus", "--effort", "high"],
        ("grok", "grok-4", "low"): ["-m", "grok-4", "--effort", "low"],
        ("codex", "gpt-5.2-codex", "xhigh"): [
            "-m", "gpt-5.2-codex", "-c", 'model_reasoning_effort="xhigh"'],
        ("shell", "", ""): [],
        ("shell", "m", "e"): [],
    }

    def test_interactive_flags_match_v040_exactly(self):
        for (prov, model, effort), want in self.GOLDENS.items():
            with self.subTest(provider=prov, model=model, effort=effort):
                self.assertEqual(tc.interactive_flags(prov, model, effort),
                                 want)


class LaunchLineGoldens(unittest.TestCase):
    """build_launch_line — the exact pane command, quoting included."""

    def test_claude_launch_line(self):
        line = tc.build_launch_line("claude", "fix the bug", "/tmp/w s",
                                    model="opus", effort="high")
        self.assertEqual(
            line,
            "cd '/tmp/w s' && exec claude --model opus --effort high "
            "'fix the bug'")

    def test_promptless_launch_line(self):
        line = tc.build_launch_line("grok", "", "/tmp", model="grok-4")
        self.assertEqual(line, "cd /tmp && exec grok -m grok-4")


if __name__ == "__main__":
    unittest.main()
