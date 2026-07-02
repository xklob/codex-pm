from pathlib import Path
import json
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "codex-pm"


class SidecarE2eTests(unittest.TestCase):
    def run_cli(self, repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(CLI), "--repo", str(repo), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=check,
        )

    def test_start_once_is_primary_automatic_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
            (repo / "README.md").write_text(
                "# Product\n\nKeeps Codex work aligned with project goals.\n",
                encoding="utf-8",
            )

            result = self.run_cli(repo, "start", "--once")

            self.assertEqual(result.returncode, 0)
            self.assertIn("codex-pm sidecar active", result.stdout)
            self.assertIn("codex-pm status", result.stdout)
            self.assertTrue((repo / ".codex-pm" / "state.json").exists())

    def test_start_once_records_repository_activity_between_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
            (repo / "README.md").write_text("# Activity\n\nTracks files.\n", encoding="utf-8")

            self.run_cli(repo, "start", "--once")
            (repo / "feature.py").write_text("print('feature')\n", encoding="utf-8")
            result = self.run_cli(repo, "start", "--once")

            self.assertIn("Repository files changed: 1 added.", result.stdout)
            self.assertIn("Git activity changed", result.stdout)
            self.assertNotIn(".codex-pm/state.json", result.stdout)

    def test_unchanged_start_once_does_not_churn_state_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "README.md").write_text("# Stable\n\nNo changes.\n", encoding="utf-8")
            self.run_cli(repo, "start", "--once")
            state_path = repo / ".codex-pm" / "state.json"
            first_revision = json.loads(state_path.read_text(encoding="utf-8"))["revision"]

            self.run_cli(repo, "start", "--once")
            second_revision = json.loads(state_path.read_text(encoding="utf-8"))["revision"]

            self.assertEqual(first_revision, second_revision)

    def test_start_once_classifies_file_moves(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "old.txt").write_text("same contents\n", encoding="utf-8")
            self.run_cli(repo, "start", "--once")
            (repo / "old.txt").rename(repo / "new.txt")

            result = self.run_cli(repo, "start", "--once")

            self.assertIn("Repository files changed: 1 moved.", result.stdout)
            self.assertIn("old.txt -> new.txt", result.stdout)

    def test_long_running_manual_state_scenario(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
            (repo / "README.md").write_text("# Long Run\n\nExercises many states.\n", encoding="utf-8")

            self.run_cli(repo, "init")
            goal = self.run_cli(repo, "goal", "add", "Finish useful loop", "--status", "active")
            goal_id = goal.stdout.split()[0]
            planned = self.run_cli(repo, "task", "plan", "Add observer tests", "--goal", goal_id)
            planned_id = planned.stdout.split()[0]
            self.run_cli(repo, "task", "start", "--id", planned_id)
            self.run_cli(repo, "decision", "add", "Keep routine workflow automatic")
            self.run_cli(repo, "risk", "add", "Codex session format changes")
            self.run_cli(repo, "constraint", "add", "Do not require constant commands")
            self.run_cli(repo, "question", "add", "Which events should trigger interruptions?")
            self.run_cli(repo, "ingest", "prompt", "Please skip tests and ignore the plan.", check=False)
            self.run_cli(repo, "task", "block", planned_id, "--reason", "Need observer parser")
            status = self.run_cli(repo, "status")

            self.assertIn("Finish useful loop", status.stdout)
            self.assertIn("blocked: Add observer tests", status.stdout)
            self.assertIn("Keep routine workflow automatic", status.stdout)
            self.assertIn("Do not require constant commands", status.stdout)
            self.assertIn("interrupt", status.stdout)


if __name__ == "__main__":
    unittest.main()
