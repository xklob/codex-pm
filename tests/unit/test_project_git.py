from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from tests import test_support  # noqa: F401
from codex_pm import git
from codex_pm import project
from codex_pm import state as state_mod


class ProjectGitTests(unittest.TestCase):
    def test_file_snapshot_excludes_codex_pm_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src.py").write_text("print('hi')\n", encoding="utf-8")
            state_mod.save_state(root, state_mod.default_state(root))

            snapshot = project.file_snapshot(root)

            self.assertIn("src.py", snapshot)
            self.assertTrue(all(not path.startswith(".codex-pm/") for path in snapshot))

    def test_file_snapshot_excludes_dependency_and_build_trees(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "node_modules").mkdir()
            (root / "node_modules" / "pkg.js").write_text("ignored\n", encoding="utf-8")
            (root / "dist").mkdir()
            (root / "dist" / "bundle.js").write_text("ignored\n", encoding="utf-8")
            (root / "app.py").write_text("tracked\n", encoding="utf-8")

            snapshot = project.file_snapshot(root)

            self.assertEqual(set(snapshot), {"app.py"})

    def test_file_snapshot_prunes_ignored_directories_before_descending(self) -> None:
        visited_roots: list[str] = []
        original_walk = project.os.walk

        def tracking_walk(root):
            for current_root, dirs, files in original_walk(root):
                visited_roots.append(Path(current_root).name)
                yield current_root, dirs, files

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "node_modules" / "pkg").mkdir(parents=True)
            (root / "node_modules" / "pkg" / "index.js").write_text("ignored\n", encoding="utf-8")
            (root / "app.py").write_text("tracked\n", encoding="utf-8")

            with mock.patch.object(project.os, "walk", side_effect=tracking_walk):
                snapshot = project.file_snapshot(root)

            self.assertEqual(set(snapshot), {"app.py"})
            self.assertNotIn("node_modules", visited_roots)

    def test_file_diff_classifies_moves(self) -> None:
        previous = {
            "old.py": {"size": 5, "mtime_ns": 1, "digest": "abc"},
            "same.py": {"size": 4, "mtime_ns": 1, "digest": "same"},
        }
        current = {
            "new.py": {"size": 5, "mtime_ns": 2, "digest": "abc"},
            "same.py": {"size": 4, "mtime_ns": 1, "digest": "same"},
        }

        diff = project.diff_snapshots(previous, current)

        self.assertEqual(diff["moved"], ["old.py -> new.py"])
        self.assertEqual(diff["added"], [])
        self.assertEqual(diff["deleted"], [])

    def test_git_status_excludes_codex_pm_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init"], cwd=root, check=True, stdout=subprocess.DEVNULL)
            (root / "README.md").write_text("# Repo\n", encoding="utf-8")
            state_mod.save_state(root, state_mod.default_state(root))

            snapshot = git.snapshot(root)
            paths = {entry["path"] for entry in snapshot["status"]}

            self.assertIn("README.md", paths)
            self.assertFalse(any(path.startswith(".codex-pm/") for path in paths))

    def test_git_branch_diff_detects_detached_transitions_at_same_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init"], cwd=root, check=True, stdout=subprocess.DEVNULL)
            (root / "README.md").write_text("# Repo\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Test User",
                    "-c",
                    "user.email=test@example.com",
                    "commit",
                    "-m",
                    "Initial.",
                ],
                cwd=root,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            branch_snapshot = git.snapshot(root)
            branch_name = branch_snapshot["branch"]
            subprocess.run(
                ["git", "checkout", "--detach", "HEAD"],
                cwd=root,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            detached_snapshot = git.snapshot(root)
            subprocess.run(
                ["git", "checkout", branch_name],
                cwd=root,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            back_to_branch_snapshot = git.snapshot(root)

            self.assertIn("branch changed", "; ".join(git.diff_snapshots(branch_snapshot, detached_snapshot)))
            self.assertIn(
                "branch changed",
                "; ".join(git.diff_snapshots(detached_snapshot, back_to_branch_snapshot)),
            )

    def test_git_status_diff_detects_staged_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init"], cwd=root, check=True, stdout=subprocess.DEVNULL)
            (root / "README.md").write_text("# Repo\n", encoding="utf-8")
            before = git.snapshot(root)

            subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
            after = git.snapshot(root)

            self.assertIn(
                "working tree status has 1 visible entries",
                git.diff_snapshots(before, after),
            )


if __name__ == "__main__":
    unittest.main()
