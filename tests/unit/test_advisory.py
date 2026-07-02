import unittest

from tests import test_support  # noqa: F401
from codex_pm import advisory
from codex_pm import state as state_mod


class AdvisoryTests(unittest.TestCase):
    def test_destructive_commands_interrupt(self) -> None:
        state = state_mod.default_state(".")

        advisories = advisory.analyze(state, "command", "git reset --hard HEAD")

        self.assertEqual(advisory.strongest(advisories), "interrupt")
        self.assertIn("destructive", advisories[0]["message"])

    def test_constraints_interrupt_conflicting_tooling(self) -> None:
        state = state_mod.default_state(".")
        state_mod.add_issue(state, "constraint", "Use Python standard library only")

        advisories = advisory.analyze(state, "prompt", "Let's add npm install vite")

        self.assertEqual(advisory.strongest(advisories), "interrupt")
        self.assertTrue(any("constraint" in item["message"] for item in advisories))

    def test_command_outputs_warn_on_failures(self) -> None:
        state = state_mod.default_state(".")

        advisories = advisory.analyze(state, "command_output", "Traceback: failed")

        self.assertEqual(advisory.strongest(advisories), "warning")
        self.assertIn("failure", advisories[0]["message"])

    def test_completed_task_duplicate_warns(self) -> None:
        state = state_mod.default_state(".")
        task = state_mod.add_task(state, "Write tests", status=state_mod.PLANNED)
        state_mod.set_task_status(state, task["id"], state_mod.COMPLETED)

        advisories = advisory.analyze(state, "assistant_response", "I will Write tests again.")

        self.assertEqual(advisory.strongest(advisories), "warning")
        self.assertIn("completed", advisories[0]["reasons"][0])


if __name__ == "__main__":
    unittest.main()
