from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

from . import __version__
from . import advisory
from . import render
from . import state as state_mod
from . import watch


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(normalize_global_repo(argv))
    root = state_mod.repo_root(args.repo)
    try:
        return args.func(root, args)
    except (ValueError, state_mod.StateError) as exc:
        print(f"codex-pm: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\ncodex-pm stopped.", file=sys.stderr)
        return 130


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codex-pm",
        description="Project-manager companion for Codex CLI sessions.",
    )
    parser.add_argument("--repo", default=".", help="repository root or path inside it")
    parser.add_argument("--version", action="version", version=f"codex-pm {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="initialize durable codex-pm state")
    init.set_defaults(func=cmd_init)

    start = sub.add_parser(
        "start",
        help="start the automatic sidecar loop",
        epilog="Repository can be supplied as `./codex-pm start --repo .` or `./codex-pm --repo . start`.",
    )
    start.add_argument("--interval", type=float, default=2.0, help="poll interval in seconds")
    start.add_argument("--once", action="store_true", help="run one sidecar refresh and exit")
    start.add_argument("--color", action="store_true", help="force ANSI color")
    start.set_defaults(func=cmd_start)

    status = sub.add_parser("status", help="render current project status")
    status.add_argument("--color", action="store_true", help="force ANSI color")
    status.set_defaults(func=cmd_status)

    watch_cmd = sub.add_parser("watch", help="run the live sidecar view")
    watch_cmd.add_argument("--interval", type=float, default=2.0, help="poll interval in seconds")
    watch_cmd.add_argument("--once", action="store_true", help="run one refresh and exit")
    watch_cmd.add_argument("--color", action="store_true", help="force ANSI color")
    watch_cmd.set_defaults(func=cmd_watch)

    project = sub.add_parser("project", help="manage project metadata")
    project_sub = project.add_subparsers(dest="project_command", required=True)
    purpose = project_sub.add_parser("purpose", help="show or set repository purpose")
    purpose_sub = purpose.add_subparsers(dest="purpose_command")
    purpose.set_defaults(func=cmd_project_purpose)
    purpose_set = purpose_sub.add_parser("set", help="set explicit repository purpose")
    purpose_set.add_argument("purpose")
    purpose_set.set_defaults(func=cmd_project_purpose_set)

    goal = sub.add_parser("goal", help="manage goals")
    goal_sub = goal.add_subparsers(dest="goal_command", required=True)
    goal_add = goal_sub.add_parser("add", help="add a goal")
    goal_add.add_argument("title")
    goal_add.add_argument("--description", default="")
    goal_add.add_argument("--status", choices=sorted(state_mod.GOAL_STATUSES), default=state_mod.PLANNED)
    goal_add.set_defaults(func=cmd_goal_add)
    goal_list = goal_sub.add_parser("list", help="list goals")
    goal_list.set_defaults(func=cmd_goal_list)
    goal_active = goal_sub.add_parser("set-active", help="mark a goal active")
    goal_active.add_argument("id")
    goal_active.set_defaults(func=cmd_goal_set_active)
    goal_complete = goal_sub.add_parser("complete", help="mark a goal complete")
    goal_complete.add_argument("id")
    goal_complete.set_defaults(func=cmd_goal_complete)
    goal_block = goal_sub.add_parser("block", help="mark a goal blocked")
    goal_block.add_argument("id")
    goal_block.add_argument("--reason", default="")
    goal_block.set_defaults(func=cmd_goal_block)

    task = sub.add_parser("task", help="manage tasks")
    task_sub = task.add_subparsers(dest="task_command", required=True)
    task_plan = task_sub.add_parser("plan", help="add planned work")
    add_task_args(task_plan, default_status=state_mod.PLANNED, title_required=True)
    task_plan.set_defaults(func=cmd_task_add)
    task_start = task_sub.add_parser("start", help="start a task or create active work")
    add_task_args(task_start, default_status=state_mod.ACTIVE, title_required=False)
    task_start.add_argument("--id", help="start an existing planned task")
    task_start.set_defaults(func=cmd_task_start)
    task_list = task_sub.add_parser("list", help="list tasks")
    task_list.set_defaults(func=cmd_task_list)
    task_complete = task_sub.add_parser("complete", help="mark a task complete")
    task_complete.add_argument("id")
    task_complete.set_defaults(func=cmd_task_complete)
    task_block = task_sub.add_parser("block", help="mark a task blocked")
    task_block.add_argument("id")
    task_block.add_argument("--reason", default="")
    task_block.set_defaults(func=cmd_task_block)

    decision = sub.add_parser("decision", help="record decisions")
    decision_sub = decision.add_subparsers(dest="decision_command", required=True)
    decision_add = decision_sub.add_parser("add", help="add a decision")
    decision_add.add_argument("title")
    decision_add.add_argument("--rationale", default="")
    decision_add.add_argument("--goal")
    decision_add.add_argument("--task")
    decision_add.set_defaults(func=cmd_decision_add)

    for kind in ("risk", "constraint", "question"):
        issue = sub.add_parser(kind, help=f"manage {kind}s")
        issue_sub = issue.add_subparsers(dest=f"{kind}_command", required=True)
        issue_add = issue_sub.add_parser("add", help=f"add a {kind}")
        issue_add.add_argument("title")
        issue_add.add_argument("--description", default="")
        issue_add.set_defaults(func=make_issue_add(kind))
        issue_list = issue_sub.add_parser("list", help=f"list {kind}s")
        issue_list.set_defaults(func=make_issue_list(kind))
        issue_resolve = issue_sub.add_parser("resolve", help=f"resolve a {kind}")
        issue_resolve.add_argument("id")
        issue_resolve.add_argument("--resolution", default="")
        issue_resolve.set_defaults(func=make_issue_resolve(kind))

    ingest = sub.add_parser("ingest", help="record an external Codex interaction")
    ingest.add_argument("kind", choices=["prompt", "assistant_response", "command", "command_output", "note"])
    ingest.add_argument("content", nargs="?")
    ingest.add_argument("--stdin", action="store_true", help="read content from stdin")
    ingest.set_defaults(func=cmd_ingest)

    observe = sub.add_parser(
        "observe",
        help="ingest Codex session activity (planned)",
        description="ingest Codex session activity (planned for the next implementation slice)",
    )
    observe.add_argument("--sessions-dir", help="Codex sessions directory")
    observe.set_defaults(func=cmd_observe)

    advise = sub.add_parser("advise", help="run advisory checks for text")
    advise.add_argument("kind", choices=["prompt", "assistant_response", "tool_call", "command", "command_output"])
    advise.add_argument("content", nargs="?")
    advise.add_argument("--stdin", action="store_true", help="read content from stdin")
    advise.set_defaults(func=cmd_advise)

    proxy = sub.add_parser(
        "proxy",
        help="fallback prompt proxy workflow (planned)",
        description="fallback prompt proxy workflow (planned for the next implementation slice)",
    )
    proxy.add_argument("command", nargs=argparse.REMAINDER, help="command to run after advisories")
    proxy.set_defaults(func=cmd_proxy)

    return parser


def normalize_global_repo(argv: list[str] | None) -> list[str] | None:
    if argv is None:
        argv = sys.argv[1:]
    normalized = list(argv)
    repo_args: list[str] = []
    index = 0
    while index < len(normalized):
        arg = normalized[index]
        if arg == "--repo":
            if index + 1 >= len(normalized):
                return normalized
            repo_args = ["--repo", normalized[index + 1]]
            del normalized[index : index + 2]
            continue
        if arg.startswith("--repo="):
            repo_args = ["--repo", arg.split("=", 1)[1]]
            del normalized[index]
            continue
        index += 1
    return repo_args + normalized if repo_args else normalized


def add_task_args(
    parser: argparse.ArgumentParser, default_status: str, title_required: bool
) -> None:
    parser.add_argument("title", nargs=None if title_required else "?")
    parser.add_argument("--description", default="")
    parser.add_argument("--goal")
    parser.set_defaults(default_status=default_status)


def load(root: Path) -> dict[str, Any]:
    return state_mod.load_state(root)


def save(root: Path, state: dict[str, Any]) -> None:
    state_mod.save_state(root, state)


def mutate(root: Path, mutator):
    return state_mod.update_state(root, mutator)


def cmd_init(root: Path, args: argparse.Namespace) -> int:
    state = state_mod.ensure_initialized(root)
    changed_ignore = state_mod.ensure_gitignore(root)
    print(f"Initialized {state_mod.state_path(root)}")
    if changed_ignore:
        print("Added .codex-pm/ to .gitignore")
    else:
        print(".gitignore already ignores .codex-pm/")
    if state["project"].get("purpose"):
        print(f"Purpose: {state['project']['purpose']}")
    return 0


def cmd_start(root: Path, args: argparse.Namespace) -> int:
    return run_sidecar(root, args)


def cmd_watch(root: Path, args: argparse.Namespace) -> int:
    return run_sidecar(root, args)


def run_sidecar(root: Path, args: argparse.Namespace) -> int:
    state = state_mod.ensure_initialized(root)
    state_mod.ensure_gitignore(root)
    print(watch.start_summary(state))
    if args.once:
        print(watch.run_once(root, color=args.color), end="")
        return 0
    watch.run_loop(root, interval=args.interval, color=args.color)
    return 0


def cmd_status(root: Path, args: argparse.Namespace) -> int:
    state = load(root)
    print(render.render_status(state, color=args.color), end="")
    return 0


def cmd_project_purpose(root: Path, args: argparse.Namespace) -> int:
    state = load(root)
    purpose = state["project"].get("purpose") or ""
    source = state["project"].get("purpose_source") or "unset"
    print(f"{source}: {purpose}" if purpose else "No repository purpose recorded.")
    return 0


def cmd_project_purpose_set(root: Path, args: argparse.Namespace) -> int:
    def apply(state: dict[str, Any]) -> None:
        state_mod.set_project_purpose(state, args.purpose)
        state_mod.add_activity(state, "project", "Updated repository purpose.")

    mutate(root, apply)
    print(f"Set purpose: {args.purpose}")
    return 0


def cmd_goal_add(root: Path, args: argparse.Namespace) -> int:
    def apply(state: dict[str, Any]) -> dict[str, Any]:
        goal = state_mod.add_goal(state, args.title, args.description, args.status)
        state_mod.add_activity(state, "goal", f"Added {args.status} goal `{goal['title']}`.")
        return goal

    goal = mutate(root, apply)
    print_item(goal)
    return 0


def cmd_goal_list(root: Path, args: argparse.Namespace) -> int:
    print_items(load(root).get("goals", []))
    return 0


def cmd_goal_set_active(root: Path, args: argparse.Namespace) -> int:
    def apply(state: dict[str, Any]) -> dict[str, Any]:
        goal = state_mod.set_active_goal(state, args.id)
        state_mod.add_activity(state, "goal", f"Set active goal `{goal['title']}`.")
        return goal

    goal = mutate(root, apply)
    print_item(goal)
    return 0


def cmd_goal_complete(root: Path, args: argparse.Namespace) -> int:
    def apply(state: dict[str, Any]) -> dict[str, Any]:
        goal = state_mod.set_goal_status(state, args.id, state_mod.COMPLETED)
        state_mod.add_activity(state, "goal", f"Completed goal `{goal['title']}`.")
        return goal

    goal = mutate(root, apply)
    print_item(goal)
    return 0


def cmd_goal_block(root: Path, args: argparse.Namespace) -> int:
    def apply(state: dict[str, Any]) -> dict[str, Any]:
        goal = state_mod.set_goal_status(state, args.id, state_mod.BLOCKED, args.reason)
        state_mod.add_activity(state, "goal", f"Blocked goal `{goal['title']}`.", args.reason)
        return goal

    goal = mutate(root, apply)
    print_item(goal)
    return 0


def cmd_task_add(root: Path, args: argparse.Namespace) -> int:
    def apply(state: dict[str, Any]) -> dict[str, Any]:
        task = state_mod.add_task(
            state, args.title or "", args.description, args.default_status, args.goal
        )
        state_mod.add_activity(state, "task", f"Added {task['status']} task `{task['title']}`.")
        return task

    task = mutate(root, apply)
    print_item(task)
    return 0


def cmd_task_start(root: Path, args: argparse.Namespace) -> int:
    def apply(state: dict[str, Any]) -> dict[str, Any]:
        if args.id:
            task = state_mod.set_active_task(state, args.id)
            state_mod.add_activity(state, "task", f"Started task `{task['title']}`.")
            return task
        if not args.title:
            raise ValueError("task start requires TITLE unless --id is provided")
        task = state_mod.add_task(state, args.title, args.description, state_mod.ACTIVE, args.goal)
        state_mod.add_activity(state, "task", f"Started task `{task['title']}`.")
        return task

    task = mutate(root, apply)
    print_item(task)
    return 0


def cmd_task_list(root: Path, args: argparse.Namespace) -> int:
    print_items(load(root).get("tasks", []))
    return 0


def cmd_task_complete(root: Path, args: argparse.Namespace) -> int:
    def apply(state: dict[str, Any]) -> dict[str, Any]:
        task = state_mod.set_task_status(state, args.id, state_mod.COMPLETED)
        state_mod.add_activity(state, "task", f"Completed task `{task['title']}`.")
        return task

    task = mutate(root, apply)
    print_item(task)
    return 0


def cmd_task_block(root: Path, args: argparse.Namespace) -> int:
    def apply(state: dict[str, Any]) -> dict[str, Any]:
        task = state_mod.set_task_status(state, args.id, state_mod.BLOCKED, args.reason)
        state_mod.add_activity(state, "task", f"Blocked task `{task['title']}`.", args.reason)
        return task

    task = mutate(root, apply)
    print_item(task)
    return 0


def cmd_decision_add(root: Path, args: argparse.Namespace) -> int:
    def apply(state: dict[str, Any]) -> dict[str, Any]:
        decision = state_mod.add_decision(state, args.title, args.rationale, args.goal, args.task)
        state_mod.add_activity(state, "decision", f"Recorded decision `{decision['title']}`.")
        return decision

    decision = mutate(root, apply)
    print_item(decision)
    return 0


def make_issue_add(kind: str):
    def command(root: Path, args: argparse.Namespace) -> int:
        def apply(state: dict[str, Any]) -> dict[str, Any]:
            issue = state_mod.add_issue(state, kind, args.title, args.description)
            state_mod.add_activity(state, kind, f"Added {kind} `{issue['title']}`.")
            return issue

        issue = mutate(root, apply)
        print_item(issue)
        return 0

    return command


def make_issue_list(kind: str):
    def command(root: Path, args: argparse.Namespace) -> int:
        print_items(load(root).get(state_mod.issue_collection(kind), []))
        return 0

    return command


def make_issue_resolve(kind: str):
    def command(root: Path, args: argparse.Namespace) -> int:
        def apply(state: dict[str, Any]) -> dict[str, Any]:
            issue = state_mod.resolve_issue(state, kind, args.id, args.resolution)
            state_mod.add_activity(
                state, kind, f"Resolved {kind} `{issue['title']}`.", args.resolution
            )
            return issue

        issue = mutate(root, apply)
        print_item(issue)
        return 0

    return command


def cmd_ingest(root: Path, args: argparse.Namespace) -> int:
    content = read_content(args)

    def apply(state: dict[str, Any]) -> list[dict[str, Any]]:
        state_mod.add_transcript(state, args.kind, content)
        state_mod.add_activity(state, "ingest", f"Recorded {args.kind} transcript.")
        advisories = advisory.analyze(state, args.kind, content)
        for item in advisories:
            state_mod.add_advisory(
                state,
                args.kind,
                item["severity"],
                item["message"],
                item.get("reasons", []),
                content[:120],
            )
        return advisories

    advisories = mutate(root, apply)
    print(f"Recorded {args.kind}.")
    print_advisories(advisories)
    return 1 if advisory.strongest(advisories) == "interrupt" else 0


def cmd_advise(root: Path, args: argparse.Namespace) -> int:
    content = read_content(args)
    state = load(root)
    advisories = advisory.analyze(state, args.kind, content)
    print_advisories(advisories)
    return 1 if advisory.strongest(advisories) == "interrupt" else 0


def cmd_observe(root: Path, args: argparse.Namespace) -> int:
    print(
        "Codex session observation is planned for the next implementation slice. "
        "Use `start` for the current sidecar loop."
    )
    return 2


def cmd_proxy(root: Path, args: argparse.Namespace) -> int:
    print(
        "Proxy mode is planned for the next implementation slice. "
        "Use the normal Codex CLI beside `codex-pm start` for now."
    )
    return 2


def read_content(args: argparse.Namespace) -> str:
    if args.stdin:
        return sys.stdin.read()
    if args.content is None:
        raise ValueError("content is required unless --stdin is used")
    return args.content


def print_item(item: dict[str, Any]) -> None:
    print(f"{item.get('id')} {item.get('status', '')} {item.get('title', '')}".strip())


def print_items(items: list[dict[str, Any]]) -> None:
    if not items:
        print("none")
        return
    for item in items:
        print_item(item)


def print_advisories(advisories: list[dict[str, Any]]) -> None:
    if not advisories:
        print("No advisories.")
        return
    for item in advisories:
        print(f"{item['severity']}: {item['message']}")
        for reason in item.get("reasons", []):
            print(f"  reason: {reason}")
