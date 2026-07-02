# codex-pm

`codex-pm` is a project-manager companion for using Codex on software projects.

It is intended to run alongside an active Codex CLI session and maintain the
high-level context that is easy to lose during iterative development: the
repository's purpose, major goals, planned work, active tasks, in-progress
changes, recent decisions, and open risks.

The goal is for `codex-pm` to act like a second brain and a soft guardrail while
working with Codex. Before or during Codex work, the user can run prompts,
intentions, or task ideas by `codex-pm`. It should warn when proposed work
appears to conflict with stated goals, duplicate existing work, expand scope
unnecessarily, or move the project in a counterproductive direction.

## Intended Workflow

The preferred workflow is to run `codex-pm` in a second terminal while the user
works in a separate terminal running the Codex CLI.

Ideally, `codex-pm` observes or hooks into the existing Codex CLI session. If
direct session integration is not available, `codex-pm` may provide a proxy
workflow where prompts pass through it before being sent to Codex. Proxy mode is
a fallback because the primary experience should preserve the normal Codex CLI
workflow while adding project-level awareness beside it.

## What It Tracks

`codex-pm` should maintain a durable project memory that includes:

- the overall purpose of the repository or task
- major goals, features, or milestones
- planned, active, blocked, and completed work
- the immediate task currently underway
- the medium-level goal that the current task belongs to
- recent decisions and their rationale
- open risks, constraints, and unresolved questions
- files, branches, commits, and other project activity that may affect context

Some of this information may be stated directly by the user. Over time,
`codex-pm` should also infer useful context from Codex usage, repository
structure, file changes, git activity, and project history.

## Terminal Display

The second-terminal UI should provide a live view of project state, including:

- the current immediate task
- the medium-level goal connected to that task
- major project goals or features and their current status
- recent file and git changes
- occasional colored suggestions, warnings, or notes

Suggestions should be advisory by default. `codex-pm` should check with the user
before blocking or redirecting work unless the project has been configured with
stricter guardrails.

## Project Awareness

`codex-pm` should automatically detect project activity such as:

- file creation, edits, moves, and deletions
- git branch checkouts
- commits and staged changes
- meaningful changes to project structure
- changes that may affect current goals or in-progress work

When activity is detected, `codex-pm` should update its knowledge of the
project and, when useful, summarize what changed and how it relates to current
goals.

## Background Analysis

When needed, `codex-pm` may delegate analysis to background workers or
sub-agents. These workers could inspect diffs, summarize changed files, detect
scope drift, infer progress against goals, identify risks, or keep the project
model current while the user continues working.

Background analysis should support the main project-management loop without
getting in the way of the active Codex session.

## Design Principles

- Preserve the user's normal Codex CLI workflow whenever possible.
- Keep project goals visible and actionable.
- Prefer soft warnings and useful context over heavy-handed blocking.
- Make project memory durable across sessions.
- Detect changes automatically rather than relying only on manual updates.
- Help the user avoid work that conflicts with their own stated goals.
- Stay focused on project direction, not just individual code edits.

## Status

This repository currently describes the intended direction for `codex-pm`. The
initial implementation should start with the smallest useful loop: persistent
project goals, a second-terminal status view, repository and git change
detection, and advisory checks against the user's active goals.
