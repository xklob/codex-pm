from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tests import test_support  # noqa: F401
from codex_pm import state as state_mod
from codex_pm import watch


class WatchTests(unittest.TestCase):
    def test_run_once_preserves_existing_state_while_recording_activity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Repo\n\nTracks work.\n", encoding="utf-8")
            watch.run_once(root)
            state = state_mod.load_state(root)
            goal = state_mod.add_goal(state, "Keep manual correction", status=state_mod.ACTIVE)
            state_mod.save_state(root, state)
            (root / "feature.txt").write_text("new\n", encoding="utf-8")

            output = watch.run_once(root)
            latest = state_mod.load_state(root)

            self.assertIn(goal["id"], {item["id"] for item in latest["goals"]})
            self.assertIn("Repository files changed: 1 added.", output)

    def test_run_loop_clears_screen_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stream = StringIO()

            with redirect_stdout(stream):
                watch.run_loop(root, interval=0, iterations=2)

            self.assertGreaterEqual(stream.getvalue().count("\033[2J\033[H"), 2)

    def test_run_once_does_not_reinitialize_existing_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_mod.ensure_initialized(root)

            with mock.patch.object(watch.state_mod, "ensure_initialized") as ensure:
                ensure.side_effect = AssertionError("should not initialize existing state")
                watch.run_once(root)

            ensure.assert_not_called()


if __name__ == "__main__":
    unittest.main()
