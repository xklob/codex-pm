from __future__ import annotations

from typing import Any

from . import state as state_mod


COLORS = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "cyan": "\033[36m",
}


def colorize(text: str, color: str, enabled: bool) -> str:
    if not enabled:
        return text
    return f"{COLORS[color]}{text}{COLORS['reset']}"


def render_status(state: dict[str, Any], color: bool = False) -> str:
    project = state.get("project", {})
    lines: list[str] = []
    lines.append(colorize("codex-pm status", "bold", color))
    purpose = project.get("purpose") or "No repository purpose recorded."
    purpose_source = project.get("purpose_source") or "unset"
    lines.append(f"Purpose ({purpose_source}): {purpose}")
    lines.append("")

    task = state_mod.active_task(state)
    goal = linked_goal(state, task) or state_mod.active_goal(state)
    lines.append(section("Current work", color))
    lines.append(f"Immediate task: {format_item(task)}")
    lines.append(f"Medium goal: {format_item(goal)}")
    lines.append("")

    lines.append(section("Goals", color))
    append_status_counts(lines, state.get("goals", []))
    for goal_item in recent_items(state.get("goals", []), 5):
        lines.append(f"- {goal_item['status']}: {goal_item['title']} ({goal_item['id']})")
    lines.append("")

    lines.append(section("Tasks", color))
    append_status_counts(lines, state.get("tasks", []))
    for task_item in recent_items(state.get("tasks", []), 8):
        suffix = f" -> {task_item['goal_id']}" if task_item.get("goal_id") else ""
        lines.append(
            f"- {task_item['status']}: {task_item['title']} ({task_item['id']}){suffix}"
        )
    lines.append("")

    append_issue_section(lines, "Risks", state.get("risks", []), color)
    append_issue_section(lines, "Constraints", state.get("constraints", []), color)
    append_issue_section(lines, "Questions", state.get("questions", []), color)

    lines.append(section("Recent decisions", color))
    for decision in reversed(state.get("decisions", [])[-5:]):
        rationale = f" - {decision['rationale']}" if decision.get("rationale") else ""
        lines.append(f"- {decision['title']}{rationale}")
    if not state.get("decisions"):
        lines.append("- none")
    lines.append("")

    lines.append(section("Recent activity", color))
    for item in reversed(state.get("activity", [])[-8:]):
        lines.append(f"- [{item.get('kind')}] {item.get('summary')}")
        if item.get("details"):
            lines.append(f"  details: {item.get('details')}")
    if not state.get("activity"):
        lines.append("- none")
    lines.append("")

    lines.append(section("Advisories", color))
    for advisory in reversed(state.get("advisories", [])[-8:]):
        severity = advisory.get("severity", "note")
        sev_color = {"interrupt": "red", "warning": "yellow"}.get(severity, "cyan")
        lines.append(colorize(f"- {severity}: {advisory.get('message')}", sev_color, color))
        for reason in advisory.get("reasons", [])[:3]:
            lines.append(f"  reason: {reason}")
    if not state.get("advisories"):
        lines.append("- none")

    return "\n".join(lines).rstrip() + "\n"


def section(title: str, color: bool) -> str:
    return colorize(title, "bold", color)


def format_item(item: dict[str, Any] | None) -> str:
    if not item:
        return "none"
    return f"{item.get('title')} ({item.get('status')}, {item.get('id')})"


def linked_goal(state: dict[str, Any], task: dict[str, Any] | None) -> dict[str, Any] | None:
    if not task or not task.get("goal_id"):
        return None
    try:
        return state_mod.find_item(state.get("goals", []), task["goal_id"], "goal")
    except ValueError:
        return None


def recent_items(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return list(reversed(items[-limit:]))


def append_status_counts(lines: list[str], items: list[dict[str, Any]]) -> None:
    counts: dict[str, int] = {}
    for item in items:
        counts[item.get("status", "unknown")] = counts.get(item.get("status", "unknown"), 0) + 1
    if counts:
        summary = ", ".join(f"{name}: {counts[name]}" for name in sorted(counts))
        lines.append(f"Summary: {summary}")
    else:
        lines.append("Summary: none")


def append_issue_section(
    lines: list[str], title: str, items: list[dict[str, Any]], color: bool
) -> None:
    lines.append(section(title, color))
    open_items = [item for item in items if item.get("status") == "open"]
    if not open_items:
        lines.append("- none open")
    for item in reversed(open_items[-5:]):
        detail = f" - {item['description']}" if item.get("description") else ""
        lines.append(f"- {item['title']} ({item['id']}){detail}")
    lines.append("")
