from pathlib import Path
import unittest

from tests import test_support  # noqa: F401
from codex_pm import render
from codex_pm import state as state_mod


class RenderTests(unittest.TestCase):
    def test_status_shows_active_task_medium_goal_and_open_items(self) -> None:
        state = state_mod.default_state(Path.cwd())
        goal = state_mod.add_goal(state, "Ship automatic sidecar")
        state_mod.add_task(state, "Render live status", status=state_mod.ACTIVE, goal_id=goal["id"])
        state_mod.add_issue(state, "risk", "Observer format may change")
        state_mod.add_issue(state, "constraint", "Do not require constant commands")
        state_mod.add_issue(state, "question", "How often should polling run?")

        output = render.render_status(state)

        self.assertIn("Immediate task: Render live status", output)
        self.assertIn("Medium goal: Ship automatic sidecar", output)
        self.assertIn("Observer format may change", output)
        self.assertIn("Do not require constant commands", output)
        self.assertIn("How often should polling run?", output)


if __name__ == "__main__":
    unittest.main()
