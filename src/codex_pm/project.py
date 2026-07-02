from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from .state import STATE_DIR


EXCLUDED_DIRS = {
    ".cache",
    ".git",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    STATE_DIR,
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "venv",
    ".venv",
}


def file_snapshot(
    root: str | Path,
    previous: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    root_path = Path(root).resolve()
    previous = previous or {}
    snapshot: dict[str, dict[str, Any]] = {}
    for current_root, dirs, files in os.walk(root_path):
        current_path = Path(current_root)
        dirs[:] = [
            name
            for name in dirs
            if name not in EXCLUDED_DIRS and not should_ignore(current_path / name, root_path)
        ]
        for name in files:
            path = current_path / name
            if should_ignore(path, root_path):
                continue
            if not path.is_file():
                continue
            rel = path.relative_to(root_path).as_posix()
            try:
                stat = path.stat()
            except OSError:
                continue
            previous_meta = previous.get(rel, {})
            meta = {
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
            if (
                previous_meta.get("size") == meta["size"]
                and previous_meta.get("mtime_ns") == meta["mtime_ns"]
                and previous_meta.get("digest")
            ):
                meta["digest"] = previous_meta["digest"]
            else:
                meta["digest"] = file_digest(path)
            snapshot[rel] = meta
    return snapshot


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def should_ignore(path: Path, root: Path) -> bool:
    try:
        rel_parts = path.relative_to(root).parts
    except ValueError:
        return True
    return any(part in EXCLUDED_DIRS for part in rel_parts)


def diff_snapshots(
    previous: dict[str, dict[str, Any]] | None,
    current: dict[str, dict[str, Any]],
) -> dict[str, list[str]]:
    previous = previous or {}
    previous_paths = set(previous)
    current_paths = set(current)
    added_candidates = sorted(current_paths - previous_paths)
    deleted_candidates = sorted(previous_paths - current_paths)
    moves: list[str] = []
    added_set = set(added_candidates)
    deleted_set = set(deleted_candidates)
    for old_path in deleted_candidates:
        old_meta = previous.get(old_path, {})
        for new_path in added_candidates:
            if new_path not in added_set:
                continue
            new_meta = current.get(new_path, {})
            same_size = old_meta.get("size") == new_meta.get("size")
            same_digest = old_meta.get("digest") == new_meta.get("digest")
            if same_size and same_digest:
                moves.append(f"{old_path} -> {new_path}")
                deleted_set.discard(old_path)
                added_set.discard(new_path)
                break
    added = sorted(added_set)
    deleted = sorted(deleted_set)
    modified = sorted(
        path
        for path in previous_paths & current_paths
        if previous[path] != current[path]
    )
    return {"added": added, "modified": modified, "deleted": deleted, "moved": moves}


def summarize_file_diff(diff: dict[str, list[str]]) -> str:
    parts: list[str] = []
    for key in ("added", "modified", "deleted", "moved"):
        count = len(diff.get(key, []))
        if count:
            parts.append(f"{count} {key}")
    return ", ".join(parts)
