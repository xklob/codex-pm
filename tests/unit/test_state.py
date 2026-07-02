from pathlib import Path
import os
import tempfile
import unittest

from tests import test_support  # noqa: F401
from codex_pm import state as state_mod


class StateTests(unittest.TestCase):
    def test_default_state_infers_readme_purpose(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text(
                "# Sample repo\n\nBuilds useful project management tools.\n",
                encoding="utf-8",
            )

            state = state_mod.default_state(root)

            self.assertIn("Sample repo", state["project"]["purpose"])
            self.assertEqual(state["project"]["purpose_source"], "inferred")

    def test_save_and_load_state_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = state_mod.default_state(root)
            goal = state_mod.add_goal(state, "Ship initial sidecar", status=state_mod.ACTIVE)

            path = state_mod.save_state(root, state)
            loaded = state_mod.load_state(root)

            self.assertEqual(path, root / ".codex-pm" / "state.json")
            self.assertEqual(loaded["active_goal_id"], goal["id"])
            self.assertEqual(loaded["goals"][0]["title"], "Ship initial sidecar")

    def test_corrupted_state_raises_state_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / ".codex-pm" / "state.json"
            path.parent.mkdir()
            path.write_text("{not-json", encoding="utf-8")

            with self.assertRaises(state_mod.StateError):
                state_mod.load_state(root)

    def test_stale_save_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stale = state_mod.default_state(root)
            state_mod.save_state(root, stale)
            latest = state_mod.load_state(root)
            state_mod.add_goal(latest, "Fresh update")
            state_mod.save_state(root, latest)
            state_mod.add_goal(stale, "Stale update")

            with self.assertRaises(state_mod.StateError):
                state_mod.save_state(root, stale)

    def test_transactional_updates_preserve_prior_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_mod.ensure_initialized(root)

            goal = state_mod.update_state(root, lambda state: state_mod.add_goal(state, "Manual goal"))
            state_mod.update_state(
                root,
                lambda state: state_mod.add_activity(state, "files", "Sidecar activity."),
            )
            latest = state_mod.load_state(root)

            self.assertIn(goal["id"], {item["id"] for item in latest["goals"]})
            self.assertEqual(latest["activity"][-1]["summary"], "Sidecar activity.")

    def test_malformed_stale_lock_is_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lock = root / ".codex-pm" / ".state.lock"
            lock.parent.mkdir()
            lock.write_text("", encoding="ascii")
            old_time = 1
            os.utime(lock, (old_time, old_time))

            state_mod.save_state(root, state_mod.default_state(root))

            self.assertFalse(lock.exists())

    def test_task_can_link_to_medium_goal_and_become_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = state_mod.default_state(root)
            goal = state_mod.add_goal(state, "Build observer")
            task = state_mod.add_task(
                state,
                "Parse Codex JSONL",
                status=state_mod.PLANNED,
                goal_id=goal["id"],
            )

            state_mod.set_active_task(state, task["id"])

            self.assertEqual(state["active_task_id"], task["id"])
            self.assertEqual(state["active_goal_id"], goal["id"])
            self.assertEqual(task["status"], state_mod.ACTIVE)

    def test_issue_collections_track_open_and_resolved_items(self) -> None:
        state = state_mod.default_state(Path.cwd())

        constraint = state_mod.add_issue(state, "constraint", "Use stdlib only")
        question = state_mod.add_issue(state, "question", "How should observer filter sessions?")
        state_mod.resolve_issue(state, "constraint", constraint["id"], "No dependencies added.")

        self.assertEqual(constraint["status"], state_mod.RESOLVED)
        self.assertEqual(constraint["resolution"], "No dependencies added.")
        self.assertEqual(question["status"], state_mod.OPEN)


if __name__ == "__main__":
    unittest.main()
