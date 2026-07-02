# 2026-07-02 implementation plan

## Goals

Implement the initial `codex-pm` product described in `README.md` as a usable
Python CLI that can run beside a Codex CLI session and maintain project-level
context.

## Requirements derived from README.md

- Preserve the normal Codex CLI workflow when possible.
- Provide a second-terminal live view of project state.
- Maintain durable project memory across sessions.
- Track repository purpose, goals, planned and active work, blocked and
  completed work, decisions, risks, questions, files, branches, commits, staged
  changes, and recent activity.
- Track constraints as first-class durable state alongside risks and unresolved
  questions.
- Detect file creation, edits, moves, deletions, git branch changes, commits,
  staged changes, and project-structure changes.
- Update project knowledge when activity is detected.
- Summarize detected activity in relation to active tasks and medium-level goals
  when there is enough context to make that relationship clear.
- Produce advisory notes and stronger interruptions when user inputs, assistant
  responses, tool calls, shell commands, or command outputs appear to conflict
  with goals, duplicate work, expand scope unnecessarily, or take a poorer route
  than an available alternative.
- Support a fallback proxy workflow for prompts and Codex responses when direct
  session integration is unavailable.
- Provide a primary read-only observer for existing Codex CLI session JSONL
  files so the normal Codex CLI workflow can remain intact. The observer must
  filter by repository `cwd`, parse user inputs, assistant responses, tool calls,
  and command outputs, and ignore unrelated sessions.
- Allow background analysis hooks without blocking the main project-management
  loop.

## Initial architecture

- `src/codex_pm/cli.py`: argparse entrypoint and command routing.
- `src/codex_pm/state.py`: durable JSON state model and atomic persistence.
- `src/codex_pm/git.py`: git snapshot and activity inspection helpers.
- `src/codex_pm/project.py`: repository file snapshot and project metadata
  inference, including durable repository purpose detection and overrides.
- `src/codex_pm/advisory.py`: prompt/response/activity advisory engine.
- `src/codex_pm/render.py`: terminal status rendering.
- `src/codex_pm/watch.py`: polling loop for live status and activity updates.
- `src/codex_pm/observer.py`: read-only Codex session discovery, JSONL tailing,
  event parsing, and repo-scoped ingestion for normal Codex CLI sessions.
- `src/codex_pm/proxy.py`: fallback command runner that records user prompts,
  Codex outputs, and advisory checks.
- `tests/`: unit, integration, and e2e coverage using the Python standard
  library test runner.

## State and activity boundaries

- Runtime state is stored in `.codex-pm/state.json` by default.
- `.codex-pm/` is ignored by git and excluded from repository file snapshots,
  activity summaries, dirty-file lists, and advisory checks.
- Git summaries shown by `codex-pm` filter out `.codex-pm/` paths even if the
  user has not yet committed the ignore rule.
- State writes use atomic replacement so interrupted sessions do not corrupt
  project memory.

## Codex observation strategy

- Primary mode: `codex-pm watch --observe-codex` discovers Codex JSONL sessions
  under `$CODEX_HOME/sessions` or `~/.codex/sessions`, selects sessions whose
  `session_meta.cwd` or `turn_context.cwd` matches the target repository, tails
  new records, and ingests relevant user, assistant, tool-call, and tool-output
  activity.
- Direct session observation is read-only. It must not modify Codex session
  files, require hooks, or change how the user invokes `codex`.
- In primary sidecar mode, interrupt-level advisories are surfaced immediately
  in the second-terminal status view as prominent "Are you sure?" warnings with
  concise reasons and timestamps. Because read-only observation cannot stop the
  active Codex CLI process, the acceptance target is timely, visible
  interruption rather than process blocking.
- Fallback modes: `codex-pm ingest` records externally supplied prompts,
  responses, commands, and notes; `codex-pm proxy` runs a configured command
  after advisory checks and records both sides of the interaction.
- Observer tests use synthetic JSONL session files so they are deterministic and
  do not depend on private local Codex history.

## CLI surface

- `codex-pm init`: initialize `.codex-pm/state.json` for a repository.
- `codex-pm status`: render the current project-management state once.
- `codex-pm watch`: run the second-terminal live view with polling.
- `codex-pm observe`: ingest new events from existing Codex session JSONL files
  once, useful for testing and manual refreshes.
- `codex-pm project purpose [set]`: show inferred repository purpose or set an
  explicit durable purpose override.
- `codex-pm goal add|list|set-active|complete|block`: manage durable goals.
- `codex-pm task plan|start|complete|block|list`: manage planned, active,
  completed, and blocked task states, with each task optionally linked to the
  medium-level goal it advances.
- `codex-pm decision add`: record decisions and rationale.
- `codex-pm risk add|resolve`: track risks.
- `codex-pm constraint add|resolve`: track constraints.
- `codex-pm question add|resolve`: track unresolved questions.
- `codex-pm ingest`: record a user prompt, Codex response, command, or note
  from an external workflow.
- `codex-pm advise`: run advisory checks for proposed work.
- `codex-pm proxy`: pass a prompt to a configured command, record both sides,
  and require explicit continuation for interrupt-level warnings before running.

## Test plan

- Unit tests:
  - state creation, migration, atomic save/load, and corrupted-state handling
  - goal/task/decision/risk transitions
  - file snapshot diff classification
  - git snapshot parsing for branch, commit, staged, and dirty state
  - advisory severity and reasons for conflicts, duplicates, scope expansion,
    and better-route hints
  - advisory review for user prompts, assistant responses, tool calls, shell
    commands, and command outputs
  - interrupt-level advisory gating decisions
  - terminal rendering content and color suppression
  - observer parsing for Codex JSONL `session_meta`, `turn_context`,
    `response_item`, and command-output records
  - observer/watch surfacing of interrupt-level warnings in the primary sidecar
    terminal view
  - repository purpose inference, explicit purpose override, and status rendering
  - task-to-goal links and status rendering of immediate task plus medium-level
    goal
  - planned-work transitions and rendering
  - constraint add/resolve transitions and rendering
  - unresolved-question add/resolve transitions and rendering
  - activity summaries that connect changed files or git activity back to the
    active task or medium-level goal when possible
- Integration tests:
  - CLI commands against temporary repositories
  - watch loop single-iteration behavior
  - observe command ingestion from synthetic Codex session files
  - ingest and proxy transcript recording
  - proxy exits before invoking the configured command unless the user confirms
    interrupt-level warnings
  - watch/observe path records and renders interrupt-level warnings from
    observed Codex prompts, assistant responses, tool calls, commands, and
    command outputs
  - git/file activity updates after repository edits
- E2e tests:
  - initialize a temporary git repository, add goals/tasks, edit files, commit,
    run `status`, and verify durable state
  - exercise proxy mode with a fake Codex command
  - exercise observe mode with a synthetic active Codex CLI session while the
    user continues using the normal workflow shape
  - long-running scenario with many user prompts, file changes, branches,
    commits, completed tasks, blocked tasks, decisions, and risks

## Milestones

1. Scaffold package, CLI, state store, ignore rules, exact command docs in
   `README.md` and `AGENTS.md`, and baseline tests.
2. Add project and git snapshot detection with `.codex-pm/` self-noise
   exclusion.
3. Add goal/task/decision/risk/constraint/question commands, including planned
   work states, task-to-goal links, and status rendering.
4. Add advisory checks for prompt and activity review, including
   interrupt-level pre-run gating.
5. Add Codex session observer for the primary sidecar workflow.
6. Add watch loop and proxy/ingest fallback workflows.
7. Add a background-analysis extension point that can run deterministic local
   analyzers without blocking the watch loop.
8. Expand integration and long-running e2e coverage.
9. Keep exact development, test, watch, observe, ingest, and proxy commands up
   to date in `README.md` and `AGENTS.md` as tooling changes.
10. Audit README requirements against implementation and close gaps.

## Review workflow

For each feature plan and each code change set before commit:

- Ask a sub-agent to review for correctness, missing requirements, testing
  gaps, and operational risks.
- Address all medium, high, and critical issues.
- Repeat review until no medium, high, or critical issues remain.
- Run the relevant local test commands and `git diff --check`.
- Run `rg --files` and `git status --short` before handoff.
- Commit with a short imperative summary ending in a period.
