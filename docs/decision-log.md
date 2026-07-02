# Decision log

This log records product and implementation decisions for `codex-pm`.

## 2026-07-02

- Chose Python with only the standard library for the initial implementation.
  This keeps installation light, avoids native watcher dependencies, and makes
  repository polling, git inspection, terminal rendering, and subprocess-based
  proxy workflows straightforward.
- Scoped the first implementation around the README's smallest useful loop:
  durable project memory, live status rendering, repository and git change
  detection, advisory checks against active goals, and a proxy/ingest fallback
  for Codex prompts and responses.
- Decided to store project memory inside `.codex-pm/state.json` by default and
  ignore that runtime directory in git. This gives each repository durable local
  state without committing private session context.
- Decided that repo-local state must be excluded from file-change analysis and
  `git status` summaries. `codex-pm` should never report its own state writes as
  user project activity.
- Chose a read-only Codex session observer as the primary sidecar integration
  path. On this machine, Codex CLI `0.142.5` writes JSONL session files under
  `~/.codex/sessions` with `session_meta`, `turn_context`, and `response_item`
  records. The observer will filter sessions by repository `cwd` and tail those
  files while leaving proxy and manual ingest as fallbacks.
- Planned tests across three layers: focused unit tests for state/advisory/diff
  logic, integration tests for CLI commands and polling behavior, and e2e tests
  that run the installed CLI against temporary git repositories.
