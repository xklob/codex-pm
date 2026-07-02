from __future__ import annotations

import time
from typing import Any

from . import git
from . import project
from . import render
from . import state as state_mod


def run_once(root, color: bool = False) -> str:
    if not state_mod.state_path(root).exists():
        state_mod.ensure_initialized(root)
    with state_mod.state_lock(root):
        state = state_mod.load_state(root)
        changed = refresh_activity(root, state)
        if changed:
            state_mod._save_state_unlocked(state_mod.state_path(root), state)
    return render.render_status(state, color=color)


def run_loop(
    root,
    interval: float = 2.0,
    color: bool = False,
    iterations: int | None = None,
) -> None:
    count = 0
    while True:
        output = run_once(root, color=color)
        print("\033[2J\033[H", end="")
        print(output, end="")
        count += 1
        if iterations is not None and count >= iterations:
            return
        time.sleep(interval)


def start_summary(state: dict[str, Any]) -> str:
    purpose = state.get("project", {}).get("purpose") or "No purpose recorded yet."
    return f"codex-pm sidecar active. Purpose: {purpose}"


def refresh_activity(root, state: dict[str, Any]) -> bool:
    snapshots = state.setdefault("snapshots", {})
    changed = False

    previous_files = snapshots.get("files")
    current_files = project.file_snapshot(root, previous_files)
    file_diff = project.diff_snapshots(previous_files, current_files)
    file_summary = project.summarize_file_diff(file_diff)
    if previous_files is not None and file_summary:
        paths = (
            file_diff["added"]
            + file_diff["modified"]
            + file_diff["deleted"]
            + file_diff["moved"]
        )
        state_mod.add_activity(
            state,
            "files",
            f"Repository files changed: {file_summary}.",
            details=", ".join(paths[:20]),
            paths=paths[:20],
        )
        changed = True
    if previous_files != current_files:
        snapshots["files"] = current_files
        changed = True

    current_git = git.snapshot(root)
    previous_git = snapshots.get("git")
    git_changes = git.diff_snapshots(previous_git, current_git)
    if previous_git is not None and git_changes:
        state_mod.add_activity(
            state,
            "git",
            "Git activity changed: " + "; ".join(git_changes) + ".",
        )
        changed = True
    if previous_git != current_git:
        snapshots["git"] = current_git
        changed = True
    return changed
