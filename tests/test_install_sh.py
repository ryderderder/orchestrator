"""Tests for install.sh: dependency detection/offers, Windows guidance,
the provider detection screen, and the install-source metadata that powers
`teamctl update`.

Each test runs install.sh in a sandbox: throwaway HOME and bin dir, a
restricted PATH containing only symlinks to the tools the script needs plus
per-test fakes (uname, brew, apt-get, sudo, ...), and scripted prompt
answers via TEAMCTL_TTY (the file read instead of /dev/tty).

Run with:  python3 -m unittest discover -s tests
"""

import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
INSTALL_SH = HERE.parent / "install.sh"

# real tools the installer needs even in the sandbox
REAL_TOOLS = ("bash", "sh", "mkdir", "cp", "chmod", "dirname", "cat", "id",
              "sed", "tail", "head", "date")


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

    def test_wsl_is_greeted_as_supported_linux(self):
        # WSL presents as Linux (uname=Linux) — the Windows refusal must
        # NOT fire; instead a friendly awareness line prints. /proc is
        # faked via the TEAMCTL_PROC_VERSION test seam. Honest limitation:
        # this exercises the detection logic, not a real WSL box.
        self.fake_uname("Linux")
        proc = self.root / "proc-version"
        proc.write_text("Linux version 5.15.167.4-microsoft-standard-WSL2 "
                        "(root@build) #1 SMP\n")
        r = self.run_install("--no-init", "--no-deps",
                             env_extra={"TEAMCTL_PROC_VERSION": str(proc),
                                        "WSL_DISTRO_NAME": "Ubuntu"})
        self.assertIn("detected WSL (Ubuntu) — proceeding as Linux "
                      "(supported)", r.stdout)
        self.assertNotIn("Nothing was installed", r.stderr)

    def test_plain_linux_gets_no_wsl_greeting(self):
        self.fake_uname("Linux")
        proc = self.root / "proc-version"
        proc.write_text("Linux version 6.8.0-45-generic (buildd@x) #1\n")
        r = self.run_install("--no-init", "--no-deps",
                             env_extra={"TEAMCTL_PROC_VERSION": str(proc)})
        self.assertNotIn("detected WSL", r.stdout)

    def test_missing_proc_version_is_silent(self):
        # the macOS reality: /proc/version does not exist. The WSL check
        # must stay completely silent — the launch-day live proof caught
        # `bash: line N: /proc/version: No such file or directory` as the
        # FIRST line of installer output (redirection-order bug: stderr
        # must be nulled before the input file is opened). Both earlier
        # WSL fixtures pointed at files that exist, which is exactly how
        # it slipped through — this pins the missing-file case.
        self.fake_uname("Darwin")
        r = self.run_install(
            "--no-init", "--no-deps",
            env_extra={"TEAMCTL_PROC_VERSION":
                       str(self.root / "no-such-proc-version")})
        self.assertNotIn("No such file or directory", r.stderr)
        self.assertNotIn("proc-version", r.stderr)
        self.assertNotIn("detected WSL", r.stdout)
        self.assertEqual(r.returncode, 0)

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
        # tmux is a hard requirement -> its prompt defaults to YES
        self.assertIn("Install tmux via brew? [Y/n]", r.stderr)
        self.assertIn("brew install tmux", self.pm_log())
        self.assertNotIn("still missing", r.stdout)
        # with tmux now present the installer heads into the tmux bootstrap
        self.assertIn("entering tmux", r.stdout)

    def test_blank_answer_defaults_to_installing_tmux(self):
        self.fake_uname("Darwin")
        self.fake_pm("brew", creates={"tmux": "tmux"})
        r = self.run_install(answers="\n")                  # just press Enter
        self.assertEqual(r.returncode, 0)
        self.assertIn("brew install tmux", self.pm_log())

    def test_python3_prompt_still_defaults_to_no(self):
        self.fake_uname("Darwin")
        real_tmux = shutil.which("tmux")
        if real_tmux:
            (self.fakebin / "tmux").symlink_to(real_tmux)   # tmux not missing
        self.fake("python3", "exit 1")                      # fails 3.11 probe
        self.fake_pm("brew", creates={"python": "python3"})
        # --no-init: tmux is real here and the bootstrap would exec into it
        r = self.run_install("--no-init", answers="\n")
        self.assertEqual(r.returncode, 0)
        self.assertIn("Install python3 via brew? [y/N]", r.stderr)
        self.assertEqual(self.pm_log(), "")                 # blank means NO
        self.assertIn("still missing: python3", r.stdout)

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

    # ---- PATH note (A3) -----------------------------------------------------

    def test_path_append_offered_and_applied_on_yes(self):
        # $BIN_DIR is never on the sandbox PATH -> the note fires; accepting
        # appends the export to the shell profile (A3: bare warning would be
        # wiped by the tmux takeover)
        self.fake_uname("Darwin")
        r = self.run_install("--no-init", answers="y\n",
                             env_extra={"SHELL": "/bin/zsh"})
        self.assertEqual(r.returncode, 0)
        self.assertIn("not on your PATH", r.stderr)
        self.assertIn("Append the PATH line", r.stderr)
        zshrc = self.home / ".zshrc"
        self.assertTrue(zshrc.exists())
        self.assertIn(f'export PATH="{self.bin}:$PATH"', zshrc.read_text())

    def test_path_declined_leaves_profile_untouched(self):
        self.fake_uname("Darwin")
        r = self.run_install("--no-init", answers="n\n",
                             env_extra={"SHELL": "/bin/zsh"})
        self.assertEqual(r.returncode, 0)
        self.assertIn("add it yourself", r.stderr)
        self.assertFalse((self.home / ".zshrc").exists())

    # ---- install-source metadata for `teamctl update` -----------------------

    def _meta(self):
        p = (self.home / ".local" / "state" / "agent-team"
             / "install-meta.json")
        self.assertTrue(p.exists(), "install-meta.json was not written")
        return json.loads(p.read_text())

    def test_install_records_source_metadata(self):
        self.fake_uname("Darwin")
        r = self.run_install("--no-init", answers="")
        self.assertEqual(r.returncode, 0)
        self.assertIn("recorded install source", r.stdout)
        meta = self._meta()
        self.assertEqual(meta["bin_dir"], str(self.bin))
        self.assertEqual(Path(meta["src_dir"]).resolve(),
                         INSTALL_SH.parent.resolve())
        # no git in the sandbox PATH -> the checkout counts as a local copy
        self.assertEqual(meta["source"], "local-copy")
        # version matches the single source of truth in the teamctl file
        v = re.search(r'^VERSION = "([^"]+)"',
                      (INSTALL_SH.parent / "teamctl").read_text(),
                      re.M).group(1)
        self.assertEqual(meta["version"], v)

    def test_install_records_git_clone_when_git_available(self):
        self.fake_uname("Darwin")
        real_git = shutil.which("git")
        if not real_git:
            self.skipTest("requires git")
        (self.fakebin / "git").symlink_to(real_git)
        r = self.run_install("--no-init", answers="")
        self.assertEqual(r.returncode, 0)
        meta = self._meta()
        self.assertEqual(meta["source"], "git-clone")
        self.assertTrue(meta["ref"])            # branch, or HEAD if detached

    # ---- provider detection screen ------------------------------------------

    def test_provider_screen_lattice_and_hints_when_none_installed(self):
        self.fake_uname("Darwin")
        r = self.run_install("--no-init", answers="")
        self.assertEqual(r.returncode, 0)
        self.assertIn("providers:", r.stdout)
        # teamctl's own lattice renders each provider honestly
        self.assertIn("not installed", r.stdout)
        self.assertIn("no provider CLI found", r.stdout)
        for url in ("claude.ai/install.sh", "chatgpt.com/codex/install.sh",
                    "x.ai/cli/install.sh"):
            self.assertIn(url, r.stdout)

    def test_installed_provider_is_never_offered(self):
        # an installed-but-signed-out CLI shows as locked out — its install
        # one-liner must NOT be printed; missing ones keep theirs
        self.fake_uname("Darwin")
        self.fake("claude", "exit 0")                   # claude on PATH
        r = self.run_install("--no-init", answers="")
        self.assertEqual(r.returncode, 0)
        self.assertIn("locked out", r.stdout)           # installed, no login
        self.assertNotIn("claude.ai/install.sh", r.stdout)
        self.assertIn("add more providers", r.stdout)
        self.assertIn("chatgpt.com/codex/install.sh", r.stdout)
        self.assertIn("x.ai/cli/install.sh", r.stdout)
        self.assertNotIn("no provider CLI found", r.stdout)

    # ---- tmux + init bootstrap ---------------------------------------------

    def test_no_tmux_prints_copy_paste_bootstrap(self):
        self.fake_uname("Darwin")                           # no pkg mgr, no tmux
        r = self.run_install(answers="")
        self.assertEqual(r.returncode, 0)
        self.assertIn("tmux new-session -A -s teamctl", r.stdout)

    def test_no_init_skips_bootstrap(self):
        self.fake_uname("Darwin")
        r = self.run_install("--no-init", answers="")
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("new-session", r.stdout)
        self.assertIn("teamctl init' any time", r.stdout)

    def test_already_inside_tmux_runs_init_directly(self):
        self.fake_uname("Darwin")
        real_tmux = shutil.which("tmux")
        if real_tmux:
            (self.fakebin / "tmux").symlink_to(real_tmux)
        r = self.run_install(answers="", env_extra={"TMUX": "/fake/sock,1,0"})
        self.assertEqual(r.returncode, 0)
        # TEAMCTL_TTY is not /dev/tty -> the wizard ran non-interactively
        cfg = self.home / ".config" / "agent-team" / "config.toml"
        self.assertTrue(cfg.exists(), r.stdout + r.stderr)

    def test_outside_tmux_execs_new_session_bootstrap(self):
        self.fake_uname("Darwin")
        self.fake("tmux", f'echo "tmux $*" >> "{self.log}"')
        r = self.run_install(answers="")
        self.assertEqual(r.returncode, 0)
        self.assertIn("entering tmux", r.stdout)
        log = self.pm_log()
        self.assertIn("tmux new-session -A -s teamctl", log)
        self.assertIn("teamctl init", log)
        self.assertNotIn("--custom", log)               # default = express

    def test_custom_init_flag_bootstraps_rich_wizard(self):
        self.fake_uname("Darwin")
        self.fake("tmux", f'echo "tmux $*" >> "{self.log}"')
        r = self.run_install("--custom-init", answers="")
        self.assertEqual(r.returncode, 0)
        self.assertIn("entering tmux", r.stdout)
        log = self.pm_log()
        self.assertIn("tmux new-session -A -s teamctl", log)
        self.assertIn("init --custom", log)


@unittest.skipUnless(shutil.which("bash") and shutil.which("tmux"),
                     "requires bash and tmux")
class TmuxHandoffTests(unittest.TestCase):
    """Prove the installer's exec form works in the curl|bash shape: stdin is
    a PIPE, only the controlling terminal (/dev/tty) is real, and
    `tmux new-session -A ... 0<> /dev/tty` must attach AND DRAW.

    The fd mode is load-bearing: `< "$TTYDEV"` opens the tty O_RDONLY and
    the tmux client writes its whole UI through that same fd — on a faithful
    pty the session ran but the user saw a BLACK SCREEN (~46 bytes drawn vs
    ~2k with the read-write fix). Found and verified by the demo-recorder
    teammate; the byte counts below discriminate the two shapes."""

    def _attach_and_measure(self, redir: str) -> tuple[int, bool, int]:
        """Run the installer's bootstrap shape through a faithful pty
        (stdin = pipe, controlling tty = pty). Returns (rc, marker_ran,
        bytes_drawn_on_tty)."""
        import fcntl
        import pty
        import shlex
        import threading
        import time

        real_tmux = shutil.which("tmux")
        sock = f"tchandoff{os.getpid()}{'rw' if '<>' in redir else 'ro'}"
        with tempfile.TemporaryDirectory() as td:
            marker = Path(td) / "attached-ok"
            # sleep keeps the session alive long enough for the client to
            # draw a full screen; the session then ends naturally so the
            # client exits on its own (rc 0).
            inner = f"touch {shlex.quote(str(marker))}; sleep 2"
            # the exact shape install.sh uses: resolve the device from fd 2
            # (tmux refuses a literal /dev/tty as its client terminal)
            script = ('TTYDEV="$(tty 0<&2 2>/dev/null)" || TTYDEV=""; '
                      f"exec {shlex.quote(real_tmux)} -L {sock} "
                      f"new-session -A -s teamctl {shlex.quote(inner)} "
                      f'{redir} "$TTYDEV"')
            master, slave = pty.openpty()

            def preexec():
                os.setsid()
                import termios
                fcntl.ioctl(slave, termios.TIOCSCTTY, 0)

            env = {"PATH": os.environ.get("PATH", ""), "HOME": td,
                   "TERM": "xterm-256color"}   # no TMUX: outside-tmux shape
            drawn = [0]
            try:
                p = subprocess.Popen(
                    ["bash", "-c", script], stdin=subprocess.PIPE,
                    stdout=slave, stderr=slave, env=env,
                    preexec_fn=preexec, pass_fds=(slave,), close_fds=True)
                os.close(slave)

                def drain():   # count what the user would actually SEE
                    try:
                        while True:
                            chunk = os.read(master, 4096)
                            if not chunk:
                                break
                            drawn[0] += len(chunk)
                    except OSError:
                        pass
                t = threading.Thread(target=drain, daemon=True)
                t.start()
                p.stdin.close()
                deadline = time.monotonic() + 20
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(0.25)
                ran = marker.exists()
                rc = p.wait(timeout=30)        # session ends on its own
                t.join(timeout=5)
                return rc, ran, drawn[0]
            finally:
                try:
                    os.close(master)
                except OSError:
                    pass
                subprocess.run([real_tmux, "-L", sock, "kill-server"],
                               capture_output=True)

    def test_install_sh_uses_read_write_tty_redirection(self):
        # static regression guard: the fix must not silently revert
        text = INSTALL_SH.read_text()
        self.assertIn('0<> "$TTYDEV"', text)
        self.assertNotIn('"$BOOTSTRAP_CMD" < "$TTYDEV"', text)

    def test_piped_stdin_attach_draws_ui_with_read_write_tty(self):
        rc, ran, drawn = self._attach_and_measure("0<>")
        self.assertTrue(ran, "tmux session command never ran")
        self.assertEqual(rc, 0)
        self.assertGreater(
            drawn, 500,
            f"tmux client drew only {drawn} bytes — black-screen regression")

    def test_readonly_tty_shape_is_the_black_screen(self):
        # the OLD shape: session runs, but the user sees (almost) nothing —
        # keep this to prove the byte-count assertion above discriminates.
        rc, ran, drawn = self._attach_and_measure("<")
        self.assertTrue(ran, "session should still run (that was the trap)")
        self.assertLess(drawn, 500,
                        "read-only tty unexpectedly drew a full UI; "
                        "re-check the fix's premise")


if __name__ == "__main__":
    unittest.main()
