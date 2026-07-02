from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Any

from .state import STATE_DIR


def snapshot(root: str | Path) -> dict[str, Any]:
    root_path = Path(root).resolve()
    return {
        "is_repo": is_git_repo(root_path),
        "branch": git_output(root_path, ["rev-parse", "--abbrev-ref", "HEAD"]),
        "commit": git_output(root_path, ["rev-parse", "--short", "HEAD"]),
        "status": status_porcelain(root_path),
    }


def is_git_repo(root: Path) -> bool:
    return git_output(root, ["rev-parse", "--is-inside-work-tree"]) == "true"


def git_output(root: Path, args: list[str]) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return proc.stdout.strip()


def status_porcelain(root: Path) -> list[dict[str, str]]:
    raw = git_output(root, ["status", "--porcelain=v1"])
    entries: list[dict[str, str]] = []
    for line in raw.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]
        if path == STATE_DIR or path.startswith(f"{STATE_DIR}/"):
            continue
        entries.append({"status": line[:2], "path": path})
    return entries


def diff_snapshots(previous: dict[str, Any] | None, current: dict[str, Any]) -> list[str]:
    previous = previous or {}
    changes: list[str] = []
    if "branch" in previous and previous.get("branch") != current.get("branch"):
        changes.append(f"branch changed {previous.get('branch')} -> {current.get('branch')}")
    if "commit" in previous and previous.get("commit") != current.get("commit"):
        changes.append(f"commit changed {previous.get('commit')} -> {current.get('commit')}")
    previous_status = previous.get("status") or []
    current_status = current.get("status") or []
    if previous_status != current_status:
        changes.append(f"working tree status has {len(current_status)} visible entries")
    return changes
