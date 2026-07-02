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
- Clarified that the desired user experience is not command-heavy. After
  initial setup, the user should normally start one sidecar process, point it at
  a repository, and keep working in Codex. The broader CLI surface is for setup,
  tests, manual correction, automation, and recovery, not routine operation.
- After the initial scaffold, selected the Codex session observer as the next
  implementation slice. This closes the biggest gap in the primary sidecar
  workflow: automatic awareness of Codex prompts, assistant responses, tool
  calls, and command outputs without requiring repeated manual commands.
- Set privacy boundaries for observer implementation: scope ingestion at the
  record's effective cwd rather than the whole session, baseline every
  live-discovered session file at EOF by default, require explicit backfill for
  historical imports, and store bounded observer metadata rather than full
  session dumps. Live sidecar observation reads only bytes appended after a file
  already has a persisted cursor; raw observed content and partial-line bytes
  must not be stored in `transcripts`, observer metadata, activity, or advisory
  fields.
- Planned tests across three layers: focused unit tests for state/advisory/diff
  logic, integration tests for CLI commands and polling behavior, and e2e tests
  that run the installed CLI against temporary git repositories.
