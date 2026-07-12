"""Tests for install.sh's dependency detection/offers and Windows guidance.

Each test runs install.sh in a sandbox: throwaway HOME and bin dir, a
restricted PATH containing only symlinks to the tools the script needs plus
per-test fakes (uname, brew, apt-get, sudo, ...), and scripted prompt
answers via TEAMCTL_TTY (the file read instead of /dev/tty).

Run with:  python3 -m unittest discover -s tests
"""

import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
INSTALL_SH = HERE.parent / "install.sh"

# real tools the installer needs even in the sandbox
REAL_TOOLS = ("bash", "sh", "mkdir", "cp", "chmod", "dirname", "cat", "id")


@unittest.skipUnless(shutil.which("bash"), "requires bash")
class InstallShTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        self.home = self.root / "home"
        self.bin = self.root / "bin"
        self.fakebin = self.root / "fakebin"
        for d in (self.home, self.bin, self.fakebin):
            d.mkdir()
        for tool in REAL_TOOLS:
            real = shutil.which(tool)
            if real:
                (self.fakebin / tool).symlink_to(real)
        real_py = shutil.which("python3")
        if real_py:
            (self.fakebin / "python3").symlink_to(real_py)
        self.log = self.root / "pm.log"

    def tearDown(self):
        self.tmpdir.cleanup()

    def fake(self, name: str, body: str):
        """Drop an executable fake tool into the sandbox PATH."""
        p = self.fakebin / name
        p.unlink(missing_ok=True)
        p.write_text("#!/bin/sh\n" + body + "\n")
        p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    def fake_uname(self, kernel: str):
        self.fake("uname", f'echo "{kernel}"')

    def fake_pm(self, name: str, creates: dict[str, str] | None = None):
        """A fake package manager that logs its argv; on `install <pkg>` it
        drops a working fake binary so the installer's re-check passes."""
        lines = [f'echo "{name} $*" >> "{self.log}"']
        if creates:
            lines.append('for a in "$@"; do case "$a" in')
            for pkg, binary in creates.items():
                lines.append(
                    f'  {pkg}) printf \'#!/bin/sh\\nexit 0\\n\' > "{self.fakebin}/{binary}";'
                    f' chmod +x "{self.fakebin}/{binary}" ;;')
            lines.append("esac; done")
        lines.append("exit 0")
        self.fake(name, "\n".join(lines))

    def run_install(self, *args, answers: str | None = None, env_extra=None):
        answers_file = self.root / "answers"
        answers_file.write_text(answers if answers is not None else "")
        env = {
            "HOME": str(self.home),
            "PATH": str(self.fakebin),
            "TEAMCTL_BIN_DIR": str(self.bin),
            "TEAMCTL_TTY": str(answers_file) if answers is not None
            else str(self.root / "no-such-tty"),
        }
        env.update(env_extra or {})
        return subprocess.run(
            ["bash", str(INSTALL_SH), *args],
            capture_output=True, text=True, env=env, timeout=60)

    def pm_log(self) -> str:
        return self.log.read_text() if self.log.exists() else ""

    # ---- Windows ----------------------------------------------------------

    def test_native_windows_gets_wsl_guidance_and_installs_nothing(self):
        self.fake_uname("MINGW64_NT-10.0-19045")
        r = self.run_install()
        self.assertEqual(r.returncode, 0)
        self.assertIn("WSL", r.stderr)
        self.assertIn("wsl --install", r.stderr)
        self.assertIn("Nothing was installed", r.stderr)
        self.assertFalse((self.bin / "teamctl").exists())

    # ---- dependency detection & offers -------------------------------------

    def test_missing_tmux_no_pkg_manager_prints_manual_hints(self):
        self.fake_uname("Darwin")  # no brew in sandbox PATH
        r = self.run_install()
        self.assertEqual(r.returncode, 0)
        self.assertIn("missing dependencies: tmux", r.stdout)
        self.assertIn("no supported package manager", r.stdout)
        self.assertIn("github.com/tmux/tmux", r.stdout)
        # binaries installed regardless
        self.assertTrue((self.bin / "teamctl").exists())
        # provider one-liners printed (no claude/codex/grok in sandbox)
        self.assertIn("claude.ai/install.sh", r.stdout)
        self.assertIn("chatgpt.com/codex/install.sh", r.stdout)
        self.assertIn("x.ai/cli/install.sh", r.stdout)

    def test_accepting_offer_installs_via_brew(self):
        self.fake_uname("Darwin")
        self.fake_pm("brew", creates={"tmux": "tmux"})
        r = self.run_install(answers="y\n")
        self.assertEqual(r.returncode, 0)
        self.assertIn("Install tmux via brew?", r.stderr)   # the actual prompt
        self.assertIn("brew install tmux", self.pm_log())
        self.assertNotIn("still missing", r.stdout)

    def test_declining_offer_runs_nothing_and_hints(self):
        self.fake_uname("Darwin")
        self.fake_pm("brew")
        r = self.run_install(answers="n\n")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.pm_log(), "")                 # never ran brew
        self.assertIn("still missing: tmux", r.stdout)
        self.assertIn("github.com/tmux/tmux", r.stdout)

    def test_no_tty_means_no_installs(self):
        # curl|bash with no terminal: never run a package manager
        self.fake_uname("Darwin")
        self.fake_pm("brew")
        r = self.run_install(answers=None)                  # unreadable tty
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.pm_log(), "")
        self.assertIn("still missing: tmux", r.stdout)

    def test_no_deps_flag_skips_offers(self):
        self.fake_uname("Darwin")
        self.fake_pm("brew")
        r = self.run_install("--no-deps", answers="y\ny\n")
        self.assertEqual(r.returncode, 0)
        self.assertIn("--no-deps", r.stdout)
        self.assertEqual(self.pm_log(), "")
        self.assertNotIn("Install tmux", r.stderr)          # never prompted

    def test_install_all_prompt_when_multiple_missing(self):
        self.fake_uname("Darwin")
        # python3 fails the >=3.11 probe, so both tmux and python3 are missing
        self.fake("python3", "exit 1")
        self.fake_pm("brew", creates={"tmux": "tmux", "python": "python3"})
        r = self.run_install(answers="y\n")                 # one bulk answer
        self.assertEqual(r.returncode, 0)
        self.assertIn("missing dependencies: tmux python3", r.stdout)
        self.assertIn("Install all missing dependencies (tmux python3)", r.stderr)
        log = self.pm_log()
        self.assertIn("brew install tmux", log)
        self.assertIn("brew install python", log)           # brew name for python3
        self.assertNotIn("still missing", r.stdout)

    def test_linux_sudo_is_announced_and_used(self):
        self.fake_uname("Linux")
        self.fake("id", "echo 1000")                        # non-root
        self.fake_pm("apt-get", creates={"tmux": "tmux"})
        self.fake("sudo", f'echo "sudo $*" >> "{self.log}"\n"$@"')
        r = self.run_install(answers="y\n")
        self.assertEqual(r.returncode, 0)
        self.assertIn("with sudo", r.stdout)                # announced first
        log = self.pm_log()
        self.assertIn("sudo apt-get install -y tmux", log)

    def test_unknown_flag_rejected(self):
        r = self.run_install("--bogus")
        self.assertEqual(r.returncode, 2)
        self.assertIn("unknown option", r.stderr)


if __name__ == "__main__":
    unittest.main()
