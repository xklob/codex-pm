from pathlib import Path
import json
import tempfile
import unittest

from tests import test_support  # noqa: F401
from codex_pm import observer
from codex_pm import state as state_mod


def record(record_type, payload, timestamp="2026-07-02T12:00:00+00:00"):
    return {"type": record_type, "timestamp": timestamp, "payload": payload}


def response(item_type, role=None, content=None, **extra):
    payload = {"type": item_type, **extra}
    if role:
        payload["role"] = role
    if content is not None:
        payload["content"] = [{"type": "text", "text": content}]
    return record("response_item", payload)


def write_jsonl(path: Path, records) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for item in records:
            handle.write(json.dumps(item) + "\n")


class ObserverTests(unittest.TestCase):
    def test_default_live_observation_baselines_preexisting_file_at_eof(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            sessions = Path(tmp) / "sessions"
            root.mkdir()
            session = sessions / "2026" / "07" / "02" / "rollout-test.jsonl"
            write_jsonl(
                session,
                [
                    record("session_meta", {"cwd": str(root)}),
                    response("message", role="user", content="RAW_PRIVATE_OLD"),
                ],
            )
            state = state_mod.default_state(root)

            changed = observer.observe_once(root, state, sessions_dir=sessions)

            self.assertTrue(changed)
            self.assertEqual(state["observer"]["events"], [])
            self.assertNotIn("RAW_PRIVATE_OLD", json.dumps(state))

    def test_appended_record_after_baseline_is_observed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            sessions = Path(tmp) / "sessions"
            root.mkdir()
            session = sessions / "rollout-test.jsonl"
            write_jsonl(session, [record("session_meta", {"cwd": str(root)})])
            state = state_mod.default_state(root)
            observer.observe_once(root, state, sessions_dir=sessions)
            with session.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(response("message", role="user", content="skip tests")) + "\n")

            changed = observer.observe_once(root, state, sessions_dir=sessions)

            self.assertTrue(changed)
            self.assertEqual(state["observer"]["events"][-1]["kind"], "prompt")
            self.assertEqual(state["advisories"][-1]["severity"], "interrupt")

    def test_from_start_backfills_matching_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            sessions = Path(tmp) / "sessions"
            root.mkdir()
            session = sessions / "rollout-test.jsonl"
            write_jsonl(
                session,
                [
                    record("session_meta", {"cwd": str(root)}),
                    response("message", role="assistant", content="Traceback: failed"),
                ],
            )
            state = state_mod.default_state(root)

            changed = observer.observe_once(root, state, sessions_dir=sessions, from_start=True)

            self.assertTrue(changed)
            self.assertEqual(state["observer"]["events"][-1]["kind"], "assistant_response")
            self.assertEqual(state["advisories"][-1]["severity"], "warning")

    def test_mixed_cwd_and_sibling_prefix_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            sibling = Path(tmp) / "repo-private"
            sessions = Path(tmp) / "sessions"
            root.mkdir()
            sibling.mkdir()
            session = sessions / "rollout-test.jsonl"
            write_jsonl(
                session,
                [
                    record("session_meta", {"cwd": str(sibling)}),
                    response("message", role="user", content="rm -rf ."),
                    record("turn_context", {"cwd": str(root / "subdir")}),
                    response("message", role="user", content="skip tests"),
                ],
            )
            (root / "subdir").mkdir()
            state = state_mod.default_state(root)

            observer.observe_once(root, state, sessions_dir=sessions, from_start=True)

            self.assertEqual(len(state["observer"]["events"]), 1)
            self.assertEqual(state["observer"]["events"][0]["kind"], "prompt")

    def test_invalid_cwd_values_clear_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            sessions = Path(tmp) / "sessions"
            root.mkdir()
            session = sessions / "rollout-test.jsonl"
            write_jsonl(
                session,
                [
                    record("session_meta", {"cwd": str(root)}),
                    record("turn_context", {"cwd": "relative/path"}),
                    response("message", role="user", content="skip tests"),
                ],
            )
            state = state_mod.default_state(root)

            observer.observe_once(root, state, sessions_dir=sessions, from_start=True)

            self.assertEqual(state["observer"]["events"], [])

    def test_raw_observed_content_is_not_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            sessions = Path(tmp) / "sessions"
            root.mkdir()
            secret = "RAW_PRIVATE_SENTINEL sk-testsecret"
            session = sessions / "rollout-test.jsonl"
            write_jsonl(
                session,
                [
                    record("session_meta", {"cwd": str(root)}),
                    response("message", role="user", content=f"{secret} skip tests"),
                ],
            )
            state = state_mod.default_state(root)

            observer.observe_once(root, state, sessions_dir=sessions, from_start=True)
            dumped = json.dumps(state)

            self.assertNotIn("RAW_PRIVATE_SENTINEL", dumped)
            self.assertNotIn("sk-testsecret", dumped)

    def test_symlink_session_candidate_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sessions = Path(tmp) / "sessions"
            target = Path(tmp) / "rollout-target.jsonl"
            sessions.mkdir()
            target.write_text("", encoding="utf-8")
            (sessions / "rollout-link.jsonl").symlink_to(target)

            files, _ = observer.discover_session_files(sessions, max_files=10)

            self.assertEqual(files, [])


if __name__ == "__main__":
    unittest.main()
