"""v0.5.0 worktree isolation + the land step.

Every teammate gets its own branch in its own directory; `teamctl land`
closes the loop; shutdown can never strand work. All git interaction is
exercised against SCRATCH repos created per test — never the real
checkout the suite runs from.

Run with:  python3 -m unittest tests.test_worktree
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

loader = SourceFileLoader("teamctl_worktree", str(TEAMCTL))
spec = importlib.util.spec_from_loader("teamctl_worktree", loader)
tc = importlib.util.module_from_spec(spec)
loader.exec_module(tc)

HAVE_GIT = shutil.which("git") is not None


def _run_git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=True)


@unittest.skipUnless(HAVE_GIT, "requires git")
class _WorktreeSandbox(unittest.TestCase):
    """Temp HOME + state dir + a scratch git repo with one commit."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory(prefix="teamctl-wt-")
        self.dir = Path(self.tmpdir.name)
        self._home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.dir)
        os.environ["TEAMCTL_STATE"] = str(self.dir / "state.json")
        self.repo = self.dir / "repo"
        self.repo.mkdir()
        _run_git(self.repo, "init", "-q")
        _run_git(self.repo, "config", "user.email", "t@example.com")
        _run_git(self.repo, "config", "user.name", "teamctl-tests")
        (self.repo / "README.md").write_text("hello\n")
        _run_git(self.repo, "add", "-A")
        _run_git(self.repo, "commit", "-q", "-m", "init")
        self.default_branch = _run_git(
            self.repo, "symbolic-ref", "--short", "HEAD").stdout.strip()

    def tearDown(self):
        os.environ.pop("TEAMCTL_STATE", None)
        if self._home is not None:
            os.environ["HOME"] = self._home
        self.tmpdir.cleanup()

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = tc.main(list(argv))
        return rc, out.getvalue(), err.getvalue()

    def alloc(self, role="builder"):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            return tc._alloc_worktree(role, str(self.repo))

    def commit_in(self, wt_path, name="work.txt", text="done\n",
                  msg="teammate work"):
        p = Path(wt_path) / name
        p.write_text(text)
        _run_git(wt_path, "add", "-A")
        _run_git(wt_path, "commit", "-q", "-m", msg)


class AllocTests(_WorktreeSandbox):
    def test_alloc_creates_branch_path_and_registry(self):
        wt = self.alloc("builder")
        self.assertTrue(Path(wt["path"]).is_dir())
        self.assertEqual(wt["branch"], "teamctl/builder")
        self.assertEqual(wt["repo"], str(self.repo.resolve()))
        head = _run_git(self.repo, "rev-parse", "HEAD").stdout.strip()
        self.assertEqual(wt["base_sha"], head)
        # branch really exists and points at HEAD
        tip = _run_git(self.repo, "rev-parse",
                       "teamctl/builder").stdout.strip()
        self.assertEqual(tip, head)
        # the path lives under the state dir, outside the repo
        self.assertTrue(str(wt["path"]).startswith(str(self.dir)))
        self.assertFalse(str(wt["path"]).startswith(str(self.repo)))
        # registry is the durable record
        reg = tc.load_worktree_registry()
        self.assertIn(wt["path"], reg)
        self.assertEqual(reg[wt["path"]]["role"], "builder")

    def test_existing_branch_is_refused_never_suffixed(self):
        _run_git(self.repo, "branch", "teamctl/builder")
        with self.assertRaises(tc.TeamctlError) as cm:
            self.alloc("builder")
        self.assertIn("already exists", str(cm.exception))
        self.assertIn("teamctl land builder", str(cm.exception))
        # no surprise -2 branch was invented
        out = _run_git(self.repo, "branch", "--list",
                       "teamctl/builder*").stdout
        self.assertNotIn("builder-2", out)

    def test_dirty_parent_gets_a_note_never_a_stash(self):
        (self.repo / "wip.txt").write_text("uncommitted\n")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            wt = tc._alloc_worktree("builder", str(self.repo))
        self.assertIn("not visible", err.getvalue())
        # the uncommitted file stayed put and is NOT in the worktree
        self.assertTrue((self.repo / "wip.txt").exists())
        self.assertFalse((Path(wt["path"]) / "wip.txt").exists())

    def test_maybe_alloc_tristate(self):
        nongit = self.dir / "plain"
        nongit.mkdir()
        # explicit --worktree outside a repo: refuse
        with self.assertRaises(tc.TeamctlError):
            tc._maybe_alloc_worktree("r", str(nongit), True)
        # config-on outside a repo: degrade with a note
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertIsNone(tc._maybe_alloc_worktree("r", str(nongit),
                                                       None))
        self.assertIn("without worktree isolation", err.getvalue())
        # --no-worktree inside a repo: off
        self.assertIsNone(tc._maybe_alloc_worktree("r", str(self.repo),
                                                   False))
        # config-off: off
        saved = tc.worktree_settings
        tc.worktree_settings = lambda: {"enabled": False, "dir": "",
                                        "branch_prefix": "teamctl/",
                                        "cleanup": "auto"}
        try:
            self.assertIsNone(tc._maybe_alloc_worktree("r", str(self.repo),
                                                       None))
        finally:
            tc.worktree_settings = saved

    def test_default_is_on(self):
        self.assertTrue(tc.worktree_settings()["enabled"])


class UniqueWorkTests(_WorktreeSandbox):
    def test_clean_fresh_worktree_has_no_unique_work(self):
        wt = self.alloc()
        unique, detail = tc._worktree_unique_work(wt)
        self.assertFalse(unique)
        self.assertIn("no new commits", detail)

    def test_dirty_files_are_unique_work(self):
        wt = self.alloc()
        (Path(wt["path"]) / "x.txt").write_text("x")
        unique, detail = tc._worktree_unique_work(wt)
        self.assertTrue(unique)
        self.assertIn("uncommitted", detail)

    def test_unlanded_commits_are_unique_work(self):
        wt = self.alloc()
        self.commit_in(wt["path"])
        unique, detail = tc._worktree_unique_work(wt)
        self.assertTrue(unique)
        self.assertIn("un-landed", detail)

    def test_landed_branch_is_not_unique_work(self):
        wt = self.alloc()
        self.commit_in(wt["path"])
        _run_git(self.repo, "merge", "-q", "--no-ff", "-m", "land",
                 wt["branch"])
        unique, detail = tc._worktree_unique_work(wt)
        self.assertFalse(unique)
        self.assertIn("landed", detail)


class ShutdownReconcileTests(_WorktreeSandbox):
    def test_clean_worktree_removed_at_shutdown(self):
        wt = self.alloc()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            tc._shutdown_worktree("builder", wt)
        self.assertIn("removed clean worktree", out.getvalue())
        self.assertFalse(Path(wt["path"]).exists())
        res = subprocess.run(["git", "-C", str(self.repo), "rev-parse",
                              "--verify", "--quiet", "refs/heads/"
                              + wt["branch"]], capture_output=True)
        self.assertNotEqual(res.returncode, 0)          # branch gone
        self.assertEqual(tc.load_worktree_registry(), {})

    def test_unlanded_work_is_kept_and_reported_never_discarded(self):
        wt = self.alloc()
        self.commit_in(wt["path"])
        (Path(wt["path"]) / "extra.txt").write_text("also uncommitted\n")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            tc._shutdown_worktree("builder", wt)
        self.assertIn("kept worktree with un-landed work", out.getvalue())
        self.assertIn("teamctl land builder", out.getvalue())
        self.assertTrue(Path(wt["path"]).exists())
        self.assertTrue((Path(wt["path"]) / "extra.txt").exists())
        self.assertIn(wt["path"], tc.load_worktree_registry())

    def test_cleanup_keep_always_keeps(self):
        wt = self.alloc()
        saved = tc.worktree_settings
        tc.worktree_settings = lambda: {"enabled": True, "dir": "",
                                        "branch_prefix": "teamctl/",
                                        "cleanup": "keep"}
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                tc._shutdown_worktree("builder", wt)
        finally:
            tc.worktree_settings = saved
        self.assertIn("cleanup = keep", out.getvalue())
        self.assertTrue(Path(wt["path"]).exists())


class LandTests(_WorktreeSandbox):
    def test_land_orphan_merges_and_cleans_up(self):
        # the post-shutdown flow: state entry gone, registry remembers
        wt = self.alloc("builder")
        self.commit_in(wt["path"], "feature.txt", "new feature\n")
        rc, out, err = self.run_cli("land", "builder", "--yes")
        self.assertEqual(rc, 0, err)
        self.assertIn("landed 'builder'", out)
        # the work is in the default branch now
        show = _run_git(self.repo, "show",
                        f"{self.default_branch}:feature.txt").stdout
        self.assertEqual(show, "new feature\n")
        # worktree, branch, registry entry: all cleaned up
        self.assertFalse(Path(wt["path"]).exists())
        self.assertEqual(tc.load_worktree_registry(), {})

    def test_land_checkpoints_uncommitted_work_with_consent(self):
        wt = self.alloc("builder")
        (Path(wt["path"]) / "loose.txt").write_text("uncommitted work\n")
        rc, out, _ = self.run_cli("land", "builder", "--yes")
        self.assertEqual(rc, 0)
        self.assertIn("checkpointed 1 change(s)", out)
        show = _run_git(self.repo, "show",
                        f"{self.default_branch}:loose.txt").stdout
        self.assertEqual(show, "uncommitted work\n")
        # the checkpoint commit message is attributable
        log = _run_git(self.repo, "log", "--oneline", "-3").stdout
        self.assertIn("teamctl checkpoint: builder", log)

    def test_declining_the_checkpoint_cancels_the_land(self):
        wt = self.alloc("builder")
        (Path(wt["path"]) / "loose.txt").write_text("keep me\n")
        saved = tc._input
        tc._input = lambda prompt: "n"
        try:
            rc, out, _ = self.run_cli("land", "builder")
        finally:
            tc._input = saved
        self.assertEqual(rc, 1)
        self.assertIn("nothing landed", out)
        self.assertTrue((Path(wt["path"]) / "loose.txt").exists())

    def test_checkpoint_only_commits_but_does_not_merge(self):
        wt = self.alloc("builder")
        (Path(wt["path"]) / "wip.txt").write_text("wip\n")
        rc, out, _ = self.run_cli("land", "builder", "--yes",
                                  "--checkpoint-only")
        self.assertEqual(rc, 0)
        # committed on the teammate branch…
        log = _run_git(self.repo, "log", "--oneline",
                       wt["branch"]).stdout
        self.assertIn("teamctl checkpoint", log)
        # …but the default branch did not move
        res = subprocess.run(
            ["git", "-C", str(self.repo), "show",
             f"{self.default_branch}:wip.txt"], capture_output=True)
        self.assertNotEqual(res.returncode, 0)
        self.assertTrue(Path(wt["path"]).exists())      # kept for the land

    def test_land_conflict_aborts_and_reports(self):
        wt = self.alloc("builder")
        # both sides edit README differently
        (Path(wt["path"]) / "README.md").write_text("teammate version\n")
        _run_git(wt["path"], "add", "-A")
        _run_git(wt["path"], "commit", "-q", "-m", "teammate edit")
        (self.repo / "README.md").write_text("root version\n")
        _run_git(self.repo, "add", "-A")
        _run_git(self.repo, "commit", "-q", "-m", "root edit")
        rc, _, err = self.run_cli("land", "builder", "--yes")
        self.assertEqual(rc, 1)
        self.assertIn("conflicts", err)
        # the merge was aborted: tree clean, no MERGE_HEAD, work preserved
        porcelain = _run_git(self.repo, "status", "--porcelain").stdout
        self.assertEqual(porcelain.strip(), "")
        self.assertFalse((self.repo / ".git" / "MERGE_HEAD").exists())
        self.assertTrue(Path(wt["path"]).exists())

    def test_land_refuses_dirty_root(self):
        wt = self.alloc("builder")
        self.commit_in(wt["path"])
        (self.repo / "dirty.txt").write_text("x")
        rc, _, err = self.run_cli("land", "builder", "--yes")
        self.assertEqual(rc, 1)
        self.assertIn("uncommitted changes", err)
        self.assertTrue(Path(wt["path"]).exists())      # nothing touched

    def test_land_refuses_switching_branches(self):
        wt = self.alloc("builder")
        self.commit_in(wt["path"])
        rc, _, err = self.run_cli("land", "builder", "--yes",
                                  "--into", "release")
        self.assertEqual(rc, 1)
        self.assertIn("never switches your branches", err)
        self.assertTrue(Path(wt["path"]).exists())

    def test_land_nothing_to_land(self):
        self.alloc("builder")
        rc, out, _ = self.run_cli("land", "builder", "--yes")
        self.assertEqual(rc, 0)
        self.assertIn("nothing to land", out)

    def test_land_dry_run_json_plan(self):
        wt = self.alloc("builder")
        self.commit_in(wt["path"])
        (Path(wt["path"]) / "loose.txt").write_text("x")
        rc, out, _ = self.run_cli("land", "builder", "--dry-run", "--json")
        self.assertEqual(rc, 0)
        plan = json.loads(out)
        self.assertEqual(plan["role"], "builder")
        self.assertEqual(plan["branch"], wt["branch"])
        self.assertEqual(plan["unlanded_commits"], 1)
        self.assertEqual(plan["uncommitted_changes"], 1)
        self.assertEqual(plan["target"], self.default_branch)
        # a dry run changes nothing
        self.assertTrue(Path(wt["path"]).exists())
        log = _run_git(self.repo, "log", "--oneline").stdout
        self.assertNotIn("teamctl land", log)

    def test_land_refuses_live_teammate(self):
        wt = self.alloc("builder")
        tc.save_state({"teammates": {"builder": {
            "provider": "shell", "pane_id": "%77", "cwd": wt["path"],
            "mode": "interactive", "worktree": wt,
            "created_at": "2026-01-01T00:00:00"}}})
        saved_live = tc.live_pane_ids
        tc.live_pane_ids = lambda: {"%77"}
        try:
            rc, _, err = self.run_cli("land", "builder", "--yes")
        finally:
            tc.live_pane_ids = saved_live
        self.assertEqual(rc, 1)
        self.assertIn("still active", err)

    def test_unknown_role_is_honest(self):
        rc, _, err = self.run_cli("land", "ghost")
        self.assertEqual(rc, 1)
        self.assertIn("no worktree recorded", err)


class WorktreeCommandTests(_WorktreeSandbox):
    def test_list_shows_orphans_and_json(self):
        wt = self.alloc("builder")
        self.commit_in(wt["path"])
        rc, out, _ = self.run_cli("worktree", "list")
        self.assertEqual(rc, 0)
        self.assertIn("builder", out)
        self.assertIn("orphan", out)
        self.assertIn("un-landed", out)
        rc, out, _ = self.run_cli("worktree", "list", "--json")
        rows = json.loads(out)
        self.assertEqual(rows[0]["role"], "builder")
        self.assertTrue(rows[0]["unique_work"])
        self.assertFalse(rows[0]["owner_alive"])

    def test_prune_removes_only_provably_clean(self):
        clean = self.alloc("cleaner")
        dirty = self.alloc("writer")
        (Path(dirty["path"]) / "x.txt").write_text("x")
        rc, out, _ = self.run_cli("worktree", "prune", "--dry-run")
        self.assertEqual(rc, 0)
        self.assertIn("(dry-run) pruned cleaner", out)
        self.assertTrue(Path(clean["path"]).exists())   # dry-run: untouched
        rc, out, _ = self.run_cli("worktree", "prune")
        self.assertEqual(rc, 0)
        self.assertFalse(Path(clean["path"]).exists())
        self.assertTrue(Path(dirty["path"]).exists())
        self.assertIn("kept writer", out)
        reg = tc.load_worktree_registry()
        self.assertIn(dirty["path"], reg)
        self.assertNotIn(clean["path"], reg)

    def test_prune_never_touches_a_live_owner(self):
        wt = self.alloc("livemate")
        tc.save_state({"teammates": {"livemate": {
            "provider": "shell", "pane_id": "%9", "cwd": wt["path"],
            "mode": "interactive", "worktree": wt,
            "created_at": "2026-01-01T00:00:00"}}})
        saved_live = tc.live_pane_ids
        tc.live_pane_ids = lambda: {"%9"}
        try:
            rc, out, _ = self.run_cli("worktree", "prune")
        finally:
            tc.live_pane_ids = saved_live
        self.assertEqual(rc, 0)
        self.assertIn("owner is live", out)
        self.assertTrue(Path(wt["path"]).exists())


class NeverForceTests(_WorktreeSandbox):
    """The git-safety invariant, audited: across alloc, shutdown-cleanup,
    land, and prune, teamctl NEVER passes a force/destructive flag to
    git."""

    FORBIDDEN = {"-D", "--force", "-f", "--hard", "reset", "clean"}

    def test_no_forced_git_anywhere(self):
        seen: list[list[str]] = []
        real_git = tc._git

        def recording_git(repo, *args, **kw):
            seen.append(list(args))
            return real_git(repo, *args, **kw)

        tc._git = recording_git
        try:
            wt = self.alloc("audited")
            self.commit_in(wt["path"])
            self.run_cli("land", "audited", "--yes")
            wt2 = self.alloc("audited2")
            tc._shutdown_worktree("audited2", wt2)
            self.run_cli("worktree", "prune")
        finally:
            tc._git = real_git
        self.assertTrue(seen, "no git calls recorded?")
        for argv in seen:
            self.assertFalse(self.FORBIDDEN & set(argv),
                             f"forbidden git flag in: git {argv}")


@unittest.skipUnless(os.environ.get("TMUX") and HAVE_GIT,
                     "requires a live tmux session and git")
class WorktreeLiveTests(_WorktreeSandbox):
    """End-to-end against real panes: spawn/dispatch into a worktree of a
    scratch repo, then shutdown/land."""

    def setUp(self):
        super().setUp()
        out = tc.tmux("new-window", "-d", "-n", f"teamctl-wt-{os.getpid()}",
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
        super().tearDown()

    def _wait_status(self, hd: Path, timeout: float = 20.0) -> bool:
        import time as _t
        deadline = _t.monotonic() + timeout
        while _t.monotonic() < deadline:
            if (hd / "status").exists():
                return True
            _t.sleep(0.3)
        return False

    def test_spawn_worktree_clean_shutdown_removes(self):
        rc, out, _ = self.run_cli("spawn", "wt_mate", "--provider", "shell",
                                  "--cwd", str(self.repo))
        self.assertEqual(rc, 0, out)
        info = tc.load_state()["teammates"]["wt_mate"]
        wt = info.get("worktree")
        self.assertTrue(wt, "spawn in a git repo must allocate a worktree "
                            "by default")
        self.assertEqual(info["cwd"], wt["path"])
        self.assertTrue(Path(wt["path"]).is_dir())
        rc, out, _ = self.run_cli("shutdown", "wt_mate")
        self.assertEqual(rc, 0)
        self.assertIn("removed clean worktree", out)
        self.assertFalse(Path(wt["path"]).exists())

    def test_dispatch_writes_in_worktree_then_lands(self):
        rc, out, _ = self.run_cli(
            "dispatch", "wt_writer", "--provider", "shell",
            "--task", "echo made-in-worktree > artifact.txt",
            "--cwd", str(self.repo))
        self.assertEqual(rc, 0, out)
        info = tc.load_state()["teammates"]["wt_writer"]
        wt = info["worktree"]
        hd = Path(info["handoff"])
        self.assertTrue(self._wait_status(hd), "task never finished")
        # the write landed in the WORKTREE, not the repo
        self.assertTrue((Path(wt["path"]) / "artifact.txt").exists())
        self.assertFalse((self.repo / "artifact.txt").exists())
        rc, out, err = self.run_cli("shutdown", "wt_writer")
        self.assertEqual(rc, 0, out + err)
        self.assertIn("kept worktree with un-landed work", out)
        rc, out, _ = self.run_cli("land", "wt_writer", "--yes")
        self.assertEqual(rc, 0, out)
        self.assertTrue((self.repo / "artifact.txt").exists())
        self.assertFalse(Path(wt["path"]).exists())


if __name__ == "__main__":
    unittest.main()
