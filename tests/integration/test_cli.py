from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "codex-pm"


class CliIntegrationTests(unittest.TestCase):
    def run_cli(self, repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(CLI), "--repo", str(repo), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=check,
        )

    def test_init_goal_task_and_status_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
            (repo / "README.md").write_text("# Demo\n\nTracks Codex work.\n", encoding="utf-8")

            init = self.run_cli(repo, "init")
            goal = self.run_cli(repo, "goal", "add", "Build sidecar", "--status", "active")
            goal_id = goal.stdout.split()[0]
            task = self.run_cli(
                repo,
                "task",
                "start",
                "Watch Codex session",
                "--goal",
                goal_id,
            )
            task_id = task.stdout.split()[0]
            status = self.run_cli(repo, "status")

            self.assertIn("Initialized", init.stdout)
            self.assertTrue((repo / ".codex-pm" / "state.json").exists())
            self.assertIn(".codex-pm/", (repo / ".gitignore").read_text(encoding="utf-8"))
            self.assertIn(task_id, status.stdout)
            self.assertIn("Medium goal: Build sidecar", status.stdout)

    def test_repo_option_accepts_file_inside_repository(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
            readme = repo / "README.md"
            readme.write_text("# File Path Repo\n\nResolves from a file.\n", encoding="utf-8")

            init = subprocess.run(
                [str(CLI), "init", "--repo", str(readme)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            status = subprocess.run(
                [str(CLI), "status", "--repo", str(readme)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )

            self.assertIn(str(repo / ".codex-pm" / "state.json"), init.stdout)
            self.assertIn("File Path Repo", status.stdout)

    def test_advise_interrupt_returns_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            result = self.run_cli(repo, "advise", "command", "rm -rf .", check=False)

            self.assertEqual(result.returncode, 1)
            self.assertIn("interrupt", result.stdout)

    def test_project_purpose_set_is_durable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self.run_cli(repo, "project", "purpose", "set", "Manage Codex project context.")

            purpose = self.run_cli(repo, "project", "purpose")
            status = self.run_cli(repo, "status")

            self.assertIn("explicit: Manage Codex project context.", purpose.stdout)
            self.assertIn("Manage Codex project context.", status.stdout)

    def test_planned_observe_and_proxy_commands_have_help(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            observe = self.run_cli(repo, "observe", "--help")
            proxy = self.run_cli(repo, "proxy", "--help")

            self.assertIn("ingest Codex session activity", observe.stdout)
            self.assertIn("fallback prompt proxy workflow", proxy.stdout)

    def test_planned_observe_and_proxy_commands_are_explicitly_future_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            observe = self.run_cli(repo, "observe", check=False)
            proxy = self.run_cli(repo, "proxy", check=False)

            self.assertEqual(observe.returncode, 2)
            self.assertEqual(proxy.returncode, 2)
            self.assertIn("planned for the next implementation slice", observe.stdout)
            self.assertIn("planned for the next implementation slice", proxy.stdout)


if __name__ == "__main__":
    unittest.main()
