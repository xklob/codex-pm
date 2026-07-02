from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Any
from uuid import uuid4


STATE_DIR = ".codex-pm"
STATE_FILE = "state.json"
STATE_VERSION = 1

ACTIVE = "active"
BLOCKED = "blocked"
COMPLETED = "completed"
OPEN = "open"
PLANNED = "planned"
RESOLVED = "resolved"

GOAL_STATUSES = {PLANNED, ACTIVE, BLOCKED, COMPLETED}
TASK_STATUSES = {PLANNED, ACTIVE, BLOCKED, COMPLETED}
ISSUE_STATUSES = {OPEN, RESOLVED}


class StateError(RuntimeError):
    """Raised when durable project state cannot be loaded or used."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:10]}"


def repo_root(start: str | Path) -> Path:
    start_path = Path(start).resolve()
    git_start = start_path.parent if start_path.is_file() else start_path
    try:
        proc = subprocess.run(
            ["git", "-C", str(git_start), "rev-parse", "--show-toplevel"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return git_start
    return Path(proc.stdout.strip()).resolve()


def state_path(root: str | Path) -> Path:
    return Path(root).resolve() / STATE_DIR / STATE_FILE


def default_state(root: str | Path) -> dict[str, Any]:
    now = utc_now()
    root_path = Path(root).resolve()
    purpose = infer_project_purpose(root_path)
    return {
        "version": STATE_VERSION,
        "revision": 0,
        "created_at": now,
        "updated_at": now,
        "project": {
            "root": str(root_path),
            "purpose": purpose,
            "purpose_source": "inferred" if purpose else "unset",
        },
        "goals": [],
        "active_goal_id": None,
        "tasks": [],
        "active_task_id": None,
        "decisions": [],
        "risks": [],
        "constraints": [],
        "questions": [],
        "activity": [],
        "advisories": [],
        "transcripts": [],
        "snapshots": {},
        "observer": {"sessions": {}},
        "settings": {"max_activity": 200, "max_advisories": 100, "max_transcripts": 100},
    }


def infer_project_purpose(root: str | Path) -> str:
    readme = Path(root) / "README.md"
    if not readme.exists():
        return ""
    try:
        lines = readme.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    heading = ""
    body: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not heading and stripped.startswith("# "):
            heading = stripped[2:].strip()
            continue
        if heading and stripped and not stripped.startswith("#"):
            body.append(stripped)
        if len(body) >= 2:
            break
    if heading and body:
        return f"{heading}: {' '.join(body)}"
    return heading


def load_state(root: str | Path) -> dict[str, Any]:
    path = state_path(root)
    if not path.exists():
        return default_state(root)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StateError(f"State file is not valid JSON: {path}") from exc
    except OSError as exc:
        raise StateError(f"Could not read state file: {path}") from exc
    if not isinstance(raw, dict):
        raise StateError(f"State file root must be an object: {path}")
    return migrate_state(raw, root)


def migrate_state(state: dict[str, Any], root: str | Path) -> dict[str, Any]:
    migrated = default_state(root)
    migrated.update(state)
    migrated["version"] = STATE_VERSION
    migrated.setdefault("revision", 0)
    migrated.setdefault("project", {})
    migrated["project"].setdefault("root", str(Path(root).resolve()))
    migrated["project"].setdefault("purpose", infer_project_purpose(root))
    migrated["project"].setdefault(
        "purpose_source", "inferred" if migrated["project"].get("purpose") else "unset"
    )
    for key, default in default_state(root).items():
        migrated.setdefault(key, default)
    migrated.setdefault("settings", {})
    migrated["settings"].setdefault("max_activity", 200)
    migrated["settings"].setdefault("max_advisories", 100)
    migrated["settings"].setdefault("max_transcripts", 100)
    return migrated


def save_state(root: str | Path, state: dict[str, Any]) -> Path:
    path = state_path(root)
    with state_lock(root):
        current_revision = current_state_revision(path)
        incoming_revision = int(state.get("revision", 0))
        if incoming_revision < current_revision:
            raise StateError("State changed on disk; reload before saving.")
        return _save_state_unlocked(path, state)


def update_state(
    root: str | Path,
    mutator: Callable[[dict[str, Any]], Any],
) -> Any:
    path = state_path(root)
    with state_lock(root):
        state = load_state(root)
        result = mutator(state)
        _save_state_unlocked(path, state)
        return result


def _save_state_unlocked(path: Path, state: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    state["revision"] = int(state.get("revision", 0)) + 1
    state["updated_at"] = utc_now()
    payload = json.dumps(state, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=f".{STATE_FILE}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            tmp.write(payload)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return path


def current_state_revision(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if not isinstance(raw, dict):
        return 0
    try:
        return int(raw.get("revision", 0))
    except (TypeError, ValueError):
        return 0


class state_lock:
    def __init__(self, root: str | Path):
        self.path = state_path(root).parent / ".state.lock"
        self.fd: int | None = None

    def __enter__(self) -> "state_lock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + 10
        while True:
            try:
                self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError:
                if self._lock_is_stale():
                    try:
                        self.path.unlink()
                    except FileNotFoundError:
                        pass
                    continue
                if time.monotonic() >= deadline:
                    raise StateError(f"Timed out waiting for state lock: {self.path}")
                time.sleep(0.05)
        os.write(self.fd, str(os.getpid()).encode("ascii"))
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def _lock_is_stale(self) -> bool:
        try:
            age = time.time() - os.path.getmtime(self.path)
        except OSError:
            return False
        try:
            raw = self.path.read_text(encoding="ascii").strip()
            pid = int(raw)
        except (OSError, ValueError):
            return age > 10
        if not raw:
            return age > 10
        if pid <= 0:
            return age > 10
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        return False


def ensure_initialized(root: str | Path) -> dict[str, Any]:
    if state_path(root).exists():
        return load_state(root)
    state = default_state(root)
    save_state(root, state)
    return state


def ensure_gitignore(root: str | Path) -> bool:
    path = Path(root) / ".gitignore"
    existing = ""
    if path.exists():
        existing = path.read_text(encoding="utf-8")
    lines = existing.splitlines()
    if STATE_DIR + "/" in {line.strip() for line in lines}:
        return False
    if existing and not existing.endswith("\n"):
        existing += "\n"
    atomic_write_text(path, existing + STATE_DIR + "/\n")
    return True


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def set_project_purpose(state: dict[str, Any], purpose: str, source: str = "explicit") -> None:
    state["project"]["purpose"] = purpose.strip()
    state["project"]["purpose_source"] = source


def add_goal(
    state: dict[str, Any],
    title: str,
    description: str = "",
    status: str = PLANNED,
) -> dict[str, Any]:
    if status not in GOAL_STATUSES:
        raise ValueError(f"Invalid goal status: {status}")
    now = utc_now()
    goal = {
        "id": new_id("goal"),
        "title": title.strip(),
        "description": description.strip(),
        "status": status,
        "created_at": now,
        "updated_at": now,
        "blocked_reason": "",
        "completed_at": "",
    }
    state["goals"].append(goal)
    if status == ACTIVE:
        set_active_goal(state, goal["id"])
    return goal


def find_item(items: list[dict[str, Any]], item_id: str, label: str) -> dict[str, Any]:
    for item in items:
        if item.get("id") == item_id:
            return item
    raise ValueError(f"Unknown {label} id: {item_id}")


def set_active_goal(state: dict[str, Any], goal_id: str) -> dict[str, Any]:
    goal = find_item(state["goals"], goal_id, "goal")
    now = utc_now()
    for existing in state["goals"]:
        if existing.get("status") == ACTIVE:
            existing["status"] = PLANNED
            existing["updated_at"] = now
    goal["status"] = ACTIVE
    goal["updated_at"] = now
    state["active_goal_id"] = goal_id
    return goal


def set_goal_status(
    state: dict[str, Any], goal_id: str, status: str, reason: str = ""
) -> dict[str, Any]:
    if status not in GOAL_STATUSES:
        raise ValueError(f"Invalid goal status: {status}")
    if status == ACTIVE:
        return set_active_goal(state, goal_id)
    goal = find_item(state["goals"], goal_id, "goal")
    goal["status"] = status
    goal["updated_at"] = utc_now()
    if status == BLOCKED:
        goal["blocked_reason"] = reason.strip()
    if status == COMPLETED:
        goal["completed_at"] = utc_now()
    if state.get("active_goal_id") == goal_id:
        state["active_goal_id"] = None
    return goal


def add_task(
    state: dict[str, Any],
    title: str,
    description: str = "",
    status: str = PLANNED,
    goal_id: str | None = None,
) -> dict[str, Any]:
    if status not in TASK_STATUSES:
        raise ValueError(f"Invalid task status: {status}")
    if goal_id:
        find_item(state["goals"], goal_id, "goal")
    now = utc_now()
    task = {
        "id": new_id("task"),
        "title": title.strip(),
        "description": description.strip(),
        "status": status,
        "goal_id": goal_id,
        "created_at": now,
        "updated_at": now,
        "blocked_reason": "",
        "completed_at": "",
    }
    state["tasks"].append(task)
    if status == ACTIVE:
        set_active_task(state, task["id"])
    return task


def set_active_task(state: dict[str, Any], task_id: str) -> dict[str, Any]:
    task = find_item(state["tasks"], task_id, "task")
    now = utc_now()
    for existing in state["tasks"]:
        if existing.get("status") == ACTIVE:
            existing["status"] = PLANNED
            existing["updated_at"] = now
    task["status"] = ACTIVE
    task["updated_at"] = now
    state["active_task_id"] = task_id
    if task.get("goal_id"):
        set_active_goal(state, task["goal_id"])
    return task


def set_task_status(
    state: dict[str, Any], task_id: str, status: str, reason: str = ""
) -> dict[str, Any]:
    if status not in TASK_STATUSES:
        raise ValueError(f"Invalid task status: {status}")
    if status == ACTIVE:
        return set_active_task(state, task_id)
    task = find_item(state["tasks"], task_id, "task")
    task["status"] = status
    task["updated_at"] = utc_now()
    if status == BLOCKED:
        task["blocked_reason"] = reason.strip()
    if status == COMPLETED:
        task["completed_at"] = utc_now()
    if state.get("active_task_id") == task_id:
        state["active_task_id"] = None
    return task


def add_decision(
    state: dict[str, Any],
    title: str,
    rationale: str = "",
    goal_id: str | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    if goal_id:
        find_item(state["goals"], goal_id, "goal")
    if task_id:
        find_item(state["tasks"], task_id, "task")
    decision = {
        "id": new_id("decision"),
        "title": title.strip(),
        "rationale": rationale.strip(),
        "goal_id": goal_id,
        "task_id": task_id,
        "created_at": utc_now(),
    }
    state["decisions"].append(decision)
    return decision


def issue_collection(kind: str) -> str:
    if kind not in {"risk", "constraint", "question"}:
        raise ValueError(f"Invalid issue kind: {kind}")
    return {"risk": "risks", "constraint": "constraints", "question": "questions"}[kind]


def add_issue(
    state: dict[str, Any], kind: str, title: str, description: str = ""
) -> dict[str, Any]:
    collection = issue_collection(kind)
    issue = {
        "id": new_id(kind),
        "title": title.strip(),
        "description": description.strip(),
        "status": OPEN,
        "created_at": utc_now(),
        "resolved_at": "",
        "resolution": "",
    }
    state[collection].append(issue)
    return issue


def resolve_issue(
    state: dict[str, Any], kind: str, issue_id: str, resolution: str = ""
) -> dict[str, Any]:
    issue = find_item(state[issue_collection(kind)], issue_id, kind)
    issue["status"] = RESOLVED
    issue["resolution"] = resolution.strip()
    issue["resolved_at"] = utc_now()
    return issue


def add_activity(
    state: dict[str, Any],
    kind: str,
    summary: str,
    details: str = "",
    paths: list[str] | None = None,
    severity: str = "note",
) -> dict[str, Any]:
    item = {
        "id": new_id("activity"),
        "kind": kind,
        "summary": summary.strip(),
        "details": details.strip(),
        "paths": paths or [],
        "severity": severity,
        "created_at": utc_now(),
        "goal_id": state.get("active_goal_id"),
        "task_id": state.get("active_task_id"),
    }
    state["activity"].append(item)
    trim_collection(state["activity"], state["settings"].get("max_activity", 200))
    return item


def add_advisory(
    state: dict[str, Any],
    source_kind: str,
    severity: str,
    message: str,
    reasons: list[str] | None = None,
    source_summary: str = "",
) -> dict[str, Any]:
    item = {
        "id": new_id("advisory"),
        "source_kind": source_kind,
        "source_summary": source_summary.strip(),
        "severity": severity,
        "message": message.strip(),
        "reasons": reasons or [],
        "created_at": utc_now(),
        "goal_id": state.get("active_goal_id"),
        "task_id": state.get("active_task_id"),
    }
    state["advisories"].append(item)
    trim_collection(state["advisories"], state["settings"].get("max_advisories", 100))
    return item


def add_transcript(
    state: dict[str, Any], kind: str, content: str, source: str = "manual"
) -> dict[str, Any]:
    item = {
        "id": new_id("transcript"),
        "kind": kind,
        "content": content,
        "source": source,
        "created_at": utc_now(),
    }
    state["transcripts"].append(item)
    trim_collection(state["transcripts"], state["settings"].get("max_transcripts", 100))
    return item


def trim_collection(items: list[dict[str, Any]], max_items: int) -> None:
    if max_items <= 0:
        return
    del items[:-max_items]


def active_goal(state: dict[str, Any]) -> dict[str, Any] | None:
    goal_id = state.get("active_goal_id")
    if not goal_id:
        return None
    try:
        return find_item(state["goals"], goal_id, "goal")
    except ValueError:
        return None


def active_task(state: dict[str, Any]) -> dict[str, Any] | None:
    task_id = state.get("active_task_id")
    if not task_id:
        return None
    try:
        return find_item(state["tasks"], task_id, "task")
    except ValueError:
        return None
