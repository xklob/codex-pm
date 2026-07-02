from __future__ import annotations

from typing import Any


SEVERITIES = ("note", "warning", "interrupt")


def severity_rank(severity: str) -> int:
    try:
        return SEVERITIES.index(severity)
    except ValueError:
        return 0


def analyze(state: dict[str, Any], kind: str, content: str) -> list[dict[str, Any]]:
    text = content.strip()
    if not text:
        return []
    lowered = text.lower()
    advisories: list[dict[str, Any]] = []

    command_warning = destructive_command_advisory(kind, lowered)
    if command_warning:
        advisories.append(command_warning)

    scope_warning = scope_advisory(kind, lowered)
    if scope_warning:
        advisories.append(scope_warning)

    duplicate_warning = duplicate_advisory(state, kind, lowered)
    if duplicate_warning:
        advisories.append(duplicate_warning)

    constraint_warning = constraint_advisory(state, kind, lowered)
    if constraint_warning:
        advisories.append(constraint_warning)

    output_warning = output_advisory(kind, lowered)
    if output_warning:
        advisories.append(output_warning)

    goal_warning = goal_alignment_advisory(state, kind, lowered)
    if goal_warning:
        advisories.append(goal_warning)

    return advisories


def destructive_command_advisory(kind: str, lowered: str) -> dict[str, Any] | None:
    if kind not in {"command", "tool_call", "prompt", "assistant_response"}:
        return None
    dangerous = [
        "sudo ",
        "rm -rf",
        "git reset --hard",
        "git clean -fd",
        "git checkout --",
        "chmod -r 777",
    ]
    hits = [pattern for pattern in dangerous if pattern in lowered]
    if not hits:
        return None
    return {
        "severity": "interrupt",
        "message": "Are you sure? This looks destructive or privileged.",
        "reasons": [f"Matched command pattern `{pattern.strip()}`." for pattern in hits],
    }


def scope_advisory(kind: str, lowered: str) -> dict[str, Any] | None:
    if kind not in {"prompt", "assistant_response", "tool_call", "command"}:
        return None
    broad_patterns = [
        "rewrite everything",
        "rewrite the whole",
        "refactor everything",
        "unrelated cleanup",
        "while i'm here",
        "nice to have",
        "change the stack",
    ]
    hits = [pattern for pattern in broad_patterns if pattern in lowered]
    if not hits:
        return None
    return {
        "severity": "interrupt",
        "message": "Are you sure? This appears to expand scope beyond the active work.",
        "reasons": [f"Matched scope-expansion phrase `{pattern}`." for pattern in hits],
    }


def duplicate_advisory(
    state: dict[str, Any], kind: str, lowered: str
) -> dict[str, Any] | None:
    if kind not in {"prompt", "assistant_response", "tool_call", "command"}:
        return None
    reasons: list[str] = []
    for task in state.get("tasks", []):
        title = str(task.get("title", "")).strip()
        if not title:
            continue
        if title.lower() in lowered and task.get("status") == "completed":
            reasons.append(f"Task `{title}` is already completed.")
        elif title.lower() in lowered and task.get("status") == "active":
            reasons.append(f"Task `{title}` is already active.")
    if not reasons:
        return None
    return {
        "severity": "warning",
        "message": "This may duplicate existing tracked work.",
        "reasons": reasons,
    }


def constraint_advisory(
    state: dict[str, Any], kind: str, lowered: str
) -> dict[str, Any] | None:
    if kind not in {"prompt", "assistant_response", "tool_call", "command"}:
        return None
    reasons: list[str] = []
    open_constraints = [
        item
        for item in state.get("constraints", [])
        if item.get("status") in {None, "open"}
    ]
    for constraint in open_constraints:
        title = str(constraint.get("title", "")).lower()
        description = str(constraint.get("description", "")).lower()
        combined = f"{title} {description}"
        if "python" in combined and any(
            token in lowered for token in ["typescript", "node", "npm", "javascript"]
        ):
            reasons.append("Open constraint refers to Python, but proposed work uses JS/TS tooling.")
        if "no sudo" in combined or "do not run sudo" in combined:
            if "sudo " in lowered:
                reasons.append("Open constraint forbids sudo.")
        if "standard library" in combined and any(
            token in lowered for token in ["pip install", "npm install", "cargo add"]
        ):
            reasons.append("Open constraint prefers standard library only.")
    if not reasons:
        return None
    return {
        "severity": "interrupt",
        "message": "Are you sure? This conflicts with an open project constraint.",
        "reasons": reasons,
    }


def output_advisory(kind: str, lowered: str) -> dict[str, Any] | None:
    if kind not in {"command_output", "tool_output", "assistant_response"}:
        return None
    failure_tokens = ["traceback", "error:", "failed", "exception", "permission denied"]
    hits = [token for token in failure_tokens if token in lowered]
    if not hits:
        return None
    return {
        "severity": "warning",
        "message": "Recent output appears to contain a failure that may need attention.",
        "reasons": [f"Matched output token `{token}`." for token in hits[:3]],
    }


def goal_alignment_advisory(
    state: dict[str, Any], kind: str, lowered: str
) -> dict[str, Any] | None:
    if kind not in {"prompt", "assistant_response", "tool_call", "command"}:
        return None
    active_goal_id = state.get("active_goal_id")
    active_task_id = state.get("active_task_id")
    if not active_goal_id and not active_task_id:
        return None
    if "ignore the plan" not in lowered and "skip tests" not in lowered:
        return None
    return {
        "severity": "interrupt",
        "message": "Are you sure? This appears to conflict with the active plan.",
        "reasons": ["The text suggests ignoring the plan or skipping validation."],
    }


def strongest(advisories: list[dict[str, Any]]) -> str:
    severity = "note"
    for advisory in advisories:
        current = advisory.get("severity", "note")
        if severity_rank(current) > severity_rank(severity):
            severity = current
    return severity
