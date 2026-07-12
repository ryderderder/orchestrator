"""v0.5.0 roster resurrect: reconcile captures crash-lost teammates in
state["lost"]; `teamctl resurrect` rebuilds them — fresh sessions, said
honestly (interactive context is NOT restorable; dispatch mates resume
exactly via followup, which never needed resurrecting).

Run with:  python3 -m unittest tests.test_resurrect
"""

import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEAMCTL = HERE.parent / "teamctl"

loader = SourceFileLoader("teamctl_resurrect", str(TEAMCTL))
spec = importlib.util.spec_from_loader("teamctl_resurrect", loader)
tc = importlib.util.module_from_spec(spec)
loader.exec_module(tc)


class _ResurrectSandbox(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory(prefix="teamctl-res-")
        self.dir = Path(self.tmpdir.name)
        os.environ["TEAMCTL_STATE"] = str(self.dir / "state.json")
        self._home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.dir)
        self._tmux_env = os.environ.get("TMUX")
        os.environ["TMUX"] = "/fake/sock,1,0"
        self._live = tc.live_pane_ids
        self._open = tc._open_pane
        self._title = tc._set_pane_title
        self._enforce = tc._enforce_lead_width
        tc.live_pane_ids = lambda: set()
        self.opened: list[str] = []
        tc._open_pane = (lambda cmd, existing:
                         self.opened.append(cmd) or "%new")
        tc._set_pane_title = lambda *a, **k: None
        tc._enforce_lead_width = lambda: None

    def tearDown(self):
        tc.live_pane_ids = self._live
        tc._open_pane = self._open
        tc._set_pane_title = self._title
        tc._enforce_lead_width = self._enforce
        if self._tmux_env is None:
            os.environ.pop("TMUX", None)
        else:
            os.environ["TMUX"] = self._tmux_env
        if self._home is not None:
            os.environ["HOME"] = self._home
        os.environ.pop("TEAMCTL_STATE", None)
        self.tmpdir.cleanup()

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = tc.main(list(argv))
        return rc, out.getvalue(), err.getvalue()

    def _interactive(self, role, pane="%gone", **over):
        cwd = self.dir / "work"
        cwd.mkdir(exist_ok=True)
        entry = {"provider": "shell", "pane_id": pane, "cwd": str(cwd),
                 "model": "m1", "effort": "e1", "prompt": "original brief",
                 "mode": "interactive",
                 "created_at": "2026-01-01T00:00:00"}
        entry.update(over)
        return entry

    def seed_state(self, teammates=None, lost=None):
        state = {"teammates": teammates or {}}
        if lost:
            state["lost"] = lost
        tc.save_state(state)


class ReconcileLostTests(_ResurrectSandbox):
    def test_dropped_interactive_mate_is_captured_as_lost(self):
        self.seed_state({"gone_mate": self._interactive("gone_mate")})
        state = tc.reconcile(tc.load_state())
        self.assertNotIn("gone_mate", state["teammates"])
        self.assertIn("gone_mate", state["lost"])
        entry = state["lost"]["gone_mate"]
        self.assertEqual(entry["prompt"], "original brief")
        self.assertIn("lost_at", entry)
        # persisted, not just in-memory
        self.assertIn("gone_mate", tc.load_state()["lost"])

    def test_dispatch_mates_stay_tracked_not_lost(self):
        hd = self.dir / "worker"
        hd.mkdir()
        self.seed_state({"worker": {
            "provider": "shell", "pane_id": "%gone", "cwd": str(self.dir),
            "mode": "dispatch", "handoff": str(hd),
            "created_at": "2026-01-01T00:00:00"}})
        state = tc.reconcile(tc.load_state())
        self.assertIn("worker", state["teammates"])
        self.assertNotIn("lost", state)

    def test_lost_roster_is_capped_at_newest(self):
        lost = {f"old{i}": {"mode": "interactive",
                            "lost_at": f"2026-01-01T00:00:{i:02d}"}
                for i in range(tc.LOST_CAP)}
        self.seed_state({"fresh": self._interactive("fresh")}, lost)
        state = tc.reconcile(tc.load_state())
        self.assertEqual(len(state["lost"]), tc.LOST_CAP)
        self.assertIn("fresh", state["lost"])        # newest kept
        self.assertNotIn("old0", state["lost"])      # oldest pruned

    def test_explicit_shutdown_never_populates_lost(self):
        tc.live_pane_ids = lambda: {"%live"}
        saved = tc._close_pane
        tc._close_pane = lambda pane: True
        try:
            self.seed_state({"mate": self._interactive("mate",
                                                       pane="%live")})
            rc, _, _ = self.run_cli("shutdown", "mate")
        finally:
            tc._close_pane = saved
        self.assertEqual(rc, 0)
        self.assertNotIn("lost", tc.load_state())

    def test_shutdown_clears_a_lost_entry(self):
        self.seed_state({}, {"ghost": self._interactive("ghost")})
        rc, out, _ = self.run_cli("shutdown", "ghost")
        self.assertEqual(rc, 0)
        self.assertIn("cleared lost teammate 'ghost'", out)
        self.assertEqual(tc.load_state().get("lost"), {})


class ResurrectCommandTests(_ResurrectSandbox):
    def test_nothing_lost_is_honest(self):
        self.seed_state({})
        rc, out, _ = self.run_cli("resurrect")
        self.assertEqual(rc, 0)
        self.assertIn("nothing to resurrect", out)

    def test_dry_run_plans_and_changes_nothing(self):
        self.seed_state({}, {"chatty": self._interactive("chatty")})
        rc, out, _ = self.run_cli("resurrect", "--dry-run")
        self.assertEqual(rc, 0)
        self.assertIn("chatty: respawn (shell/m1", out)
        self.assertIn("FRESH session", out)
        self.assertEqual(self.opened, [])            # nothing spawned
        self.assertIn("chatty", tc.load_state()["lost"])

    def test_dry_run_json_plan(self):
        self.seed_state({}, {"chatty": self._interactive("chatty")})
        rc, out, _ = self.run_cli("resurrect", "--dry-run", "--json")
        self.assertEqual(rc, 0)
        plan = json.loads(out)
        self.assertEqual(plan["chatty"]["action"], "respawn")
        self.assertEqual(plan["chatty"]["provider"], "shell")
        self.assertEqual(plan["chatty"]["model"], "m1")

    def test_respawn_carries_recorded_settings_and_honest_prefix(self):
        self.seed_state({}, {"chatty": self._interactive("chatty")})
        rc, out, err = self.run_cli("resurrect", "--yes")
        self.assertEqual(rc, 0, err)
        self.assertEqual(len(self.opened), 1)
        launch = self.opened[0]
        self.assertIn("resurrected after a crash/reboot", launch)
        self.assertIn("NOT restored", launch)
        self.assertIn("original brief", launch)      # original prompt kept
        entry = tc.load_state()["teammates"]["chatty"]
        self.assertEqual(entry["provider"], "shell")
        self.assertEqual(entry["model"], "m1")
        self.assertEqual(entry["effort"], "e1")
        self.assertEqual(entry["cwd"], str(self.dir / "work"))
        self.assertEqual(tc.load_state().get("lost", {}), {})

    def test_unknown_role_refused(self):
        self.seed_state({}, {"chatty": self._interactive("chatty")})
        rc, _, err = self.run_cli("resurrect", "nonesuch")
        self.assertEqual(rc, 1)
        self.assertIn("not in the lost roster", err)

    def test_gone_cwd_is_an_honest_error(self):
        entry = self._interactive("wanderer")
        entry["cwd"] = str(self.dir / "vanished")
        self.seed_state({}, {"wanderer": entry})
        rc, _, err = self.run_cli("resurrect", "--yes")
        self.assertEqual(rc, 1)
        self.assertIn("no longer exists", err)
        self.assertIn("wanderer", tc.load_state()["lost"])   # kept

    def test_active_again_role_clears_stale_lost_entry(self):
        tc.live_pane_ids = lambda: {"%live"}
        self.seed_state({"chatty": self._interactive("chatty",
                                                     pane="%live")},
                        {"chatty": self._interactive("chatty")})
        rc, out, _ = self.run_cli("resurrect", "--yes")
        self.assertEqual(rc, 0)
        self.assertIn("active again", out)
        self.assertEqual(tc.load_state().get("lost", {}), {})
        self.assertEqual(self.opened, [])

    def test_lost_dispatch_mate_points_at_followup(self):
        entry = self._interactive("worker")
        entry["mode"] = "dispatch"
        self.seed_state({}, {"worker": entry})
        rc, out, _ = self.run_cli("resurrect", "--yes")
        self.assertEqual(rc, 0)
        self.assertIn("followup", out)
        self.assertIn("exact session", out)
        self.assertEqual(self.opened, [])


@unittest.skipUnless(shutil.which("git"), "requires git")
class ResurrectWorktreeTests(_ResurrectSandbox):
    def _repo(self):
        repo = self.dir / "repo"
        repo.mkdir()
        for args in (("init", "-q"),
                     ("config", "user.email", "t@example.com"),
                     ("config", "user.name", "t")):
            subprocess.run(["git", "-C", str(repo), *args], check=True,
                           capture_output=True)
        (repo / "f.txt").write_text("x\n")
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True,
                       capture_output=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "i"],
                       check=True, capture_output=True)
        return repo

    def test_surviving_worktree_is_reused(self):
        repo = self._repo()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            wt = tc._alloc_worktree("builder", str(repo))
        entry = self._interactive("builder")
        entry["cwd"] = wt["path"]
        entry["worktree"] = wt
        self.seed_state({}, {"builder": entry})
        rc, out, err2 = self.run_cli("resurrect", "--yes")
        self.assertEqual(rc, 0, err2)
        self.assertIn("reusing its worktree", out)
        new = tc.load_state()["teammates"]["builder"]
        self.assertEqual(new["cwd"], wt["path"])
        self.assertEqual(new["worktree"]["branch"], wt["branch"])
        # no second branch was invented
        res = subprocess.run(["git", "-C", str(repo), "branch", "--list",
                              "teamctl/*"], capture_output=True, text=True)
        self.assertEqual(res.stdout.count("teamctl/"), 1)

    def test_gone_worktree_reallocates_fresh_from_the_repo(self):
        repo = self._repo()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            wt = tc._alloc_worktree("builder", str(repo))
        # simulate the worktree dir lost with the machine (branch cleaned
        # too — the fully-gone case)
        subprocess.run(["git", "-C", str(repo), "worktree", "remove",
                        wt["path"]], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo), "branch", "-d",
                        wt["branch"]], check=True, capture_output=True)
        entry = self._interactive("builder")
        entry["cwd"] = wt["path"]
        entry["worktree"] = wt
        self.seed_state({}, {"builder": entry})
        rc, out, err2 = self.run_cli("resurrect", "--yes")
        self.assertEqual(rc, 0, err2)
        new = tc.load_state()["teammates"]["builder"]
        self.assertIn("worktree", new)
        self.assertTrue(Path(new["worktree"]["path"]).is_dir())

    def test_gone_worktree_with_surviving_branch_is_refused_honestly(self):
        repo = self._repo()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            wt = tc._alloc_worktree("builder", str(repo))
        subprocess.run(["git", "-C", str(repo), "worktree", "remove",
                        wt["path"]], check=True, capture_output=True)
        # branch left behind (it may hold un-landed work)
        entry = self._interactive("builder")
        entry["cwd"] = wt["path"]
        entry["worktree"] = wt
        self.seed_state({}, {"builder": entry})
        rc, _, err2 = self.run_cli("resurrect", "--yes")
        self.assertEqual(rc, 1)
        self.assertIn("already exists", err2)
        self.assertIn("builder", tc.load_state()["lost"])    # kept


class SurfacesTests(_ResurrectSandbox):
    def test_list_mentions_lost_teammates(self):
        self.seed_state({}, {"ghost": self._interactive("ghost")})
        rc, out, _ = self.run_cli("list")
        self.assertEqual(rc, 0)
        self.assertIn("lost in a crash/reboot", out)
        self.assertIn("teamctl resurrect", out)

    def test_doctor_flags_lost_teammates(self):
        self.seed_state({}, {"ghost": self._interactive("ghost")})
        status, detail = tc._check_lost()
        self.assertEqual(status, "warn")
        self.assertIn("ghost", detail)
        self.assertIn("resurrect", detail)
        self.seed_state({})
        self.assertEqual(tc._check_lost()[0], "ok")


if __name__ == "__main__":
    unittest.main()
