from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shlex
from typing import Any

from . import advisory
from . import state as state_mod


DEFAULT_MAX_FILES = 200
DEFAULT_MAX_BYTES_PER_REFRESH = 2_000_000
MAX_LINE_BYTES = 256_000
MAX_OBSERVED_EVENTS = 200
SESSION_NAME_RE = re.compile(r"rollout-.*\.jsonl$")
SECRET_RE = re.compile(
    r"(secret|token|key|password|passwd|bearer|sk-[A-Za-z0-9]|SENTINEL|RAW_PRIVATE)",
    re.IGNORECASE,
)


@dataclass
class ObservedEvent:
    kind: str
    event_type: str
    timestamp: str
    source_path: str
    offset: int
    record_id: str
    call_id: str
    safe_label: str
    analysis_text: str
    raw_text: str


def sessions_root(override: str | None = None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home).expanduser().resolve() / "sessions"
    return Path.home() / ".codex" / "sessions"


def observe_once(
    root: str | Path,
    state: dict[str, Any],
    sessions_dir: str | Path | None = None,
    *,
    enabled: bool = True,
    from_start: bool = False,
    since: str | None = None,
) -> bool:
    if not enabled:
        return False
    base = sessions_root(str(sessions_dir)) if sessions_dir else sessions_root()
    observer_state = state.setdefault("observer", {})
    observer_state.setdefault("sessions", {})
    observer_state.setdefault("events", [])
    observer_state.setdefault("baseline_at", state_mod.utc_now())
    options = observer_state.setdefault(
        "options",
        {
            "max_files": DEFAULT_MAX_FILES,
            "max_bytes_per_refresh": DEFAULT_MAX_BYTES_PER_REFRESH,
            "max_line_bytes": MAX_LINE_BYTES,
        },
    )
    max_files = int(options.get("max_files", DEFAULT_MAX_FILES))
    max_bytes = int(options.get("max_bytes_per_refresh", DEFAULT_MAX_BYTES_PER_REFRESH))
    max_line = int(options.get("max_line_bytes", MAX_LINE_BYTES))
    since_dt = parse_rfc3339(since) if since else None
    files, warning = discover_session_files(base, max_files=max_files)
    changed = False
    if warning:
        state_mod.add_activity(state, "observer", warning)
        changed = True
    bytes_remaining = max_bytes
    for path in files:
        if bytes_remaining <= 0:
            state_mod.add_activity(state, "observer", "Observer byte limit reached for this refresh.")
            changed = True
            break
        consumed, file_changed = process_session_file(
            root,
            state,
            path,
            from_start=from_start,
            since=since_dt,
            max_bytes=bytes_remaining,
            max_line_bytes=max_line,
        )
        bytes_remaining -= consumed
        changed = changed or file_changed
    return changed


def discover_session_files(base: Path, max_files: int) -> tuple[list[Path], str]:
    if not base.exists():
        return [], ""
    candidates: list[Path] = []
    warning = ""
    for current_root, dirs, files in os.walk(base):
        dirs[:] = [name for name in dirs if not (Path(current_root) / name).is_symlink()]
        for name in files:
            path = Path(current_root) / name
            try:
                stat = path.lstat()
            except OSError:
                continue
            if not SESSION_NAME_RE.match(name):
                continue
            if path.is_symlink() or not path.is_file():
                continue
            if not stat.st_mode:
                continue
            candidates.append(path)
    candidates.sort(key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True)
    if len(candidates) > max_files:
        warning = f"Observer session file limit reached; baselining newest {max_files} files."
        candidates = candidates[:max_files]
    return candidates, warning


def process_session_file(
    root: str | Path,
    state: dict[str, Any],
    path: Path,
    *,
    from_start: bool,
    since: datetime | None,
    max_bytes: int,
    max_line_bytes: int,
) -> tuple[int, bool]:
    observer_state = state.setdefault("observer", {})
    sessions = observer_state.setdefault("sessions", {})
    key = str(path.resolve())
    identity = file_identity(path)
    try:
        size = path.stat().st_size
    except OSError:
        state_mod.add_activity(state, "observer", "Observer skipped unreadable session file.")
        return 0, True

    session_state = sessions.get(key)
    if not from_start and since is None:
        if not session_state or session_state.get("identity") != identity or size < int(session_state.get("offset", 0)):
            sessions[key] = {"identity": identity, "offset": size, "size": size}
            return 0, True
        start = int(session_state.get("offset", size))
    else:
        start = 0

    consumed, events, next_offset, parse_warning = read_events(
        root,
        path,
        start,
        max_bytes=max_bytes,
        max_line_bytes=max_line_bytes,
        since=since,
    )
    changed = False
    if parse_warning:
        state_mod.add_activity(state, "observer", parse_warning)
        changed = True
    for event in events:
        if ingest_observed_event(state, event):
            changed = True
    if not from_start and since is None:
        if session_state is None:
            session_state = {}
        session_state.update({"identity": identity, "offset": next_offset, "size": size})
        sessions[key] = session_state
        changed = changed or bool(events) or next_offset != start
    return consumed, changed


def read_events(
    root: str | Path,
    path: Path,
    start: int,
    *,
    max_bytes: int,
    max_line_bytes: int,
    since: datetime | None,
) -> tuple[int, list[ObservedEvent], int, str]:
    events: list[ObservedEvent] = []
    effective_cwd: Path | None = None
    consumed = 0
    offset = start
    warning = ""
    target_root = Path(root).resolve()
    try:
        with path.open("rb") as handle:
            handle.seek(start)
            while consumed < max_bytes:
                line_start = handle.tell()
                raw = handle.readline(max_line_bytes + 1)
                if not raw:
                    offset = handle.tell()
                    break
                if not raw.endswith(b"\n"):
                    offset = line_start
                    break
                consumed += len(raw)
                if len(raw) > max_line_bytes:
                    warning = "Observer skipped oversized session line."
                    offset = handle.tell()
                    continue
                try:
                    record = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    effective_cwd = None
                    warning = "Observer skipped malformed session line and reset cwd scope."
                    offset = handle.tell()
                    continue
                record_timestamp = parse_record_timestamp(record)
                record_type = str(record.get("type", ""))
                payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
                if record_type in {"session_meta", "turn_context"}:
                    new_cwd = extract_cwd(payload)
                    effective_cwd = valid_cwd(new_cwd)
                    offset = handle.tell()
                    continue
                if since is not None:
                    if record_timestamp is None or record_timestamp < since:
                        offset = handle.tell()
                        continue
                if effective_cwd is None or not cwd_matches(target_root, effective_cwd):
                    offset = handle.tell()
                    continue
                event = classify_record(record, path, line_start, record_timestamp)
                if event:
                    events.append(event)
                offset = handle.tell()
    except OSError:
        return consumed, events, offset, "Observer skipped unreadable session file."
    return consumed, events, offset, warning


def classify_record(
    record: dict[str, Any],
    path: Path,
    offset: int,
    timestamp: datetime | None,
) -> ObservedEvent | None:
    record_type = str(record.get("type", ""))
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    if record_type == "response_item":
        item_type = str(payload.get("type", ""))
        role = str(payload.get("role", ""))
        raw_text = content_text(payload)
        if item_type == "message" and role == "user":
            kind = "prompt"
            label = "observed user message"
        elif item_type == "message" and role == "assistant":
            kind = "assistant_response"
            label = "observed assistant message"
        elif item_type in {"function_call", "tool_search_call", "custom_tool_call"}:
            shell = extract_shell_command(payload)
            if shell:
                return make_event("command", "shell_command", shell, payload, path, offset, timestamp)
            kind = "tool_call"
            label = safe_tool_label(payload)
            raw_text = raw_text or json.dumps(payload, sort_keys=True)
        elif item_type in {"function_call_output", "tool_search_output", "custom_tool_call_output"}:
            kind = "command_output"
            label = "observed tool output"
            raw_text = raw_text or str(payload.get("output", ""))
        else:
            return None
        return make_event(kind, item_type, raw_text, payload, path, offset, timestamp, label)
    if record_type == "event_msg" and str(payload.get("type", "")).endswith("exec_command_end"):
        raw = "\n".join(str(payload.get(name, "")) for name in ("stdout", "stderr") if payload.get(name))
        return make_event("command_output", "exec_command_end", raw, payload, path, offset, timestamp, "observed command output")
    return None


def make_event(
    kind: str,
    event_type: str,
    raw_text: str,
    payload: dict[str, Any],
    path: Path,
    offset: int,
    timestamp: datetime | None,
    label: str | None = None,
) -> ObservedEvent:
    safe_label = sanitize_label(label or safe_tool_label(payload) or kind)
    return ObservedEvent(
        kind=kind,
        event_type=event_type,
        timestamp=(timestamp or datetime.now(timezone.utc)).isoformat(),
        source_path=str(path.resolve()),
        offset=offset,
        record_id=str(payload.get("id", "")),
        call_id=str(payload.get("call_id", "")),
        safe_label=safe_label,
        analysis_text=raw_text,
        raw_text=raw_text,
    )


def ingest_observed_event(state: dict[str, Any], event: ObservedEvent) -> bool:
    observer_state = state.setdefault("observer", {})
    seen = observer_state.setdefault("seen", [])
    dedupe = dedupe_key(event)
    if dedupe in seen:
        return False
    seen.append(dedupe)
    del seen[:-1000]
    observed_events = observer_state.setdefault("events", [])
    observed_events.append(
        {
            "kind": event.kind,
            "event_type": event.event_type,
            "timestamp": event.timestamp,
            "label": event.safe_label,
            "redacted": True,
            "dedupe": dedupe,
        }
    )
    del observed_events[:-MAX_OBSERVED_EVENTS]
    state_mod.add_activity(
        state,
        "observer",
        f"Observed {event.kind}: {event.safe_label}.",
        severity="note",
    )
    for item in advisory.analyze(state, event.kind, event.analysis_text):
        state_mod.add_advisory(
            state,
            event.kind,
            item["severity"],
            sanitize_advisory_message(item["message"], event.kind),
            sanitize_reasons(item.get("reasons", [])),
            source_summary=f"observed {event.kind}",
        )
    return True


def dedupe_key(event: ObservedEvent) -> str:
    stable_id = event.record_id or event.call_id
    return "|".join([event.source_path, str(event.offset), event.kind, event.event_type, stable_id])


def file_identity(path: Path) -> str:
    try:
        stat = path.stat()
    except OSError:
        return "missing"
    return f"{stat.st_dev}:{stat.st_ino}:{stat.st_mtime_ns}"


def extract_cwd(payload: dict[str, Any]) -> Any:
    return payload.get("cwd") or payload.get("current_working_directory")


def valid_cwd(value: Any) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.startswith("~") or "$" in raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        return None
    try:
        resolved = path.resolve(strict=False)
    except OSError:
        return None
    return resolved


def cwd_matches(root: Path, cwd: Path) -> bool:
    try:
        cwd.relative_to(root)
    except ValueError:
        return False
    return True


def parse_record_timestamp(record: dict[str, Any]) -> datetime | None:
    for value in (record.get("timestamp"), (record.get("payload") or {}).get("timestamp")):
        if isinstance(value, str):
            parsed = parse_rfc3339(value)
            if parsed:
                return parsed
    return None


def parse_rfc3339(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def content_text(payload: dict[str, Any]) -> str:
    content = payload.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return ""


def safe_tool_label(payload: dict[str, Any]) -> str:
    name = payload.get("name") or payload.get("namespace") or payload.get("type") or "tool"
    return sanitize_label(str(name))


def extract_shell_command(payload: dict[str, Any]) -> str:
    name = str(payload.get("name", ""))
    namespace = str(payload.get("namespace", ""))
    arguments = payload.get("arguments")
    text = ""
    if isinstance(arguments, str):
        text = arguments
    elif isinstance(arguments, dict):
        for key in ("cmd", "command", "shell_command"):
            if isinstance(arguments.get(key), str):
                text = arguments[key]
                break
    if name in {"exec_command", "shell", "run"} or namespace in {"functions"}:
        return text
    return ""


def sanitize_label(value: str) -> str:
    value = value.strip()
    if not value or SECRET_RE.search(value):
        return "redacted"
    try:
        parts = shlex.split(value)
    except ValueError:
        parts = value.split()
    if not parts:
        return "redacted"
    executable = Path(parts[0]).name or parts[0]
    if SECRET_RE.search(executable):
        return "redacted"
    return executable[:80]


def sanitize_advisory_message(message: str, kind: str) -> str:
    if SECRET_RE.search(message):
        return f"Observed {kind} triggered an advisory."
    return message


def sanitize_reasons(reasons: list[str]) -> list[str]:
    sanitized: list[str] = []
    for reason in reasons[:5]:
        if SECRET_RE.search(reason):
            sanitized.append("Redacted observer advisory reason.")
        else:
            sanitized.append(reason)
    return sanitized
