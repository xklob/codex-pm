# 2026-07-02 observer plan

## Goal

Make `codex-pm start --repo <path>` automatically observe the active Codex CLI
session tail for the target repository while preserving the user's normal Codex
workflow and avoiding accidental ingestion of unrelated historical or private
session content.

## Scope

- Add `src/codex_pm/observer.py` for session discovery, JSONL parsing,
  repo-scoped filtering, offset tracking, and event ingestion.
- Wire observation into `watch.run_once()` so the main sidecar loop ingests new
  Codex activity on each refresh.
- Replace the `codex-pm observe` placeholder with a functional one-shot command
  for tests, manual refreshes, and debugging.
- Keep `proxy` as an explicit planned placeholder for a later slice.

## Behavior

- Discover sessions under `--sessions-dir`, `$CODEX_HOME/sessions`, or
  `~/.codex/sessions`. Discovery uses `lstat` and regular-file checks and must
  not follow symlinks or process non-regular files.
- Apply repository scoping at the record level, not the whole-session level.
  The observer keeps the latest `cwd` from `session_meta` and `turn_context`
  records while reading a JSONL file, and ingests only records whose effective
  cwd resolves to the target repository. Records from mixed-cwd sessions are
  skipped unless the current record scope matches the target repository.
- Repository cwd matching uses resolved path equality or descendant semantics
  only. A record cwd inside the target repository is relevant; sibling-prefix
  paths such as `/repo-private` are not relevant to `/repo`.
- Context cwd values are fail-closed. Missing, non-string, empty, relative,
  shell-expanded, user-expanded, or unresolvable cwd values are invalid. Invalid
  cwd values do not resolve against the observer process cwd and do not retain
  stale scope; they invalidate effective cwd until the next valid
  `session_meta` or `turn_context` record.
- Default sidecar observation is privacy-safe: when `start` or `watch` first
  enables observation for a sessions directory, it immediately snapshots every
  preexisting Codex-like JSONL session file into persistent observer state with
  its current EOF offset, file identity, and size without parsing file contents.
  Default observation never reads pre-baseline bytes from any file, matching or
  not. Every session file first seen by live sidecar observation is baselined at
  EOF. The sidecar reads only bytes appended after it already has a persisted
  cursor for that file. Historical byte-0 reads require an explicit
  `observe --from-start` or `observe --since <timestamp>` command.
- Track per-file offsets in `.codex-pm/state.json` so repeated refreshes and
  process restarts ingest only new JSONL records. The baseline is persisted, so
  `start --once` followed by another `start --once` reads only appended bytes.
  Files first discovered after a baseline has been established are also
  baselined at EOF by default. This fail-closed rule applies even when a file
  appears newly created, copied, touched, rotated, or replaced. The tradeoff is
  that the sidecar may miss records written before its first poll sees a new
  file, but it never backfills potentially historical private bytes without
  explicit user intent.
- Offset state includes file size and inode/device where available, but no raw
  line buffers. If a line is partial, keep the offset before that line and
  retry on the next poll; partial bytes are memory-only and must not be persisted.
  If a file shrinks, is replaced, or rotates, treat it as a new file and apply
  the selected start policy. For explicit backfill, `--from-start` reads from
  byte 0 and `--since` filters records by record timestamp, not file mtime.
  Backfill uses a separate scan cursor and never rewrites the default live offset
  below its persisted EOF baseline. Ingested observed events use a stable dedupe
  key of session path, file identity, byte offset, event type, and record id or
  call id when available.
- Parse `response_item` payload envelopes and other known session records, then
  ingest:
  - user `message` records as `prompt`
  - assistant `message` records as `assistant_response`
  - `function_call`, `tool_search_call`, and `custom_tool_call` records as
    `tool_call`
  - shell command invocations extracted from function/tool call arguments as
    first-class `command` events
  - `function_call_output`, `tool_search_output`, `custom_tool_call_output`,
    and command completion event records as `command_output`
- Store compact observer metadata, event types, timestamps, redaction status,
  advisory ids, and recent activity, not full private session dumps. Raw prompt,
  assistant, tool-output, command-output, and shell-command bodies must never be
  persisted by the observer, including prefixes, short snippets, advisory
  `message`, advisory `source_summary`, advisory `reasons`, activity `summary`,
  activity `details`, or observer metadata fields. Shell command persistence
  uses structured executable-only metadata by default: sanitized executable/tool
  name, event type, cwd match, and redaction status. The executable/tool name is
  also subject to sentinel and secret-like redaction. If argument parsing,
  executable/tool-name sanitization, or redaction is uncertain, persist only a
  generic command/tool type and mark the event as redacted.
- Observed prompts, assistant responses, tool calls, shell commands, and outputs
  must not be stored as raw `transcripts`. Observer state uses a separate
  bounded metadata collection and advisory/activity entries. Tests must assert
  full sentinel raw text, partial-prefix sentinel text, and secret-like sentinel
  values are absent from `.codex-pm/state.json`.
- Run advisory checks for each ingested prompt, assistant response, tool call,
  shell command, and command output.
- Surface interrupt-level observer advisories in the same status view used for
  manual `ingest` advisories. Because session observation is read-only, these
  interruptions are timely visible warnings in the sidecar, not process-blocking
  stops in the active Codex CLI. Observer-generated advisory messages use
  sanitized templates or advisory codes only; they must not interpolate raw
  observed content.
- Ignore malformed JSONL lines and unrelated sessions while recording a warning
  activity item for repeated parse failures. Malformed JSONL lines or
  schema-drift context records invalidate the effective cwd until the next valid
  `session_meta` or `turn_context` record, so subsequent content cannot inherit
  stale in-repo scope.
- The observer is read-only with respect to Codex session files. Tests must
  assert that session file contents and mtimes are unchanged after observation.
- Bound session discovery work per refresh. Unreadable files are skipped with a
  warning activity item. If the sessions tree exceeds configured file or byte
  limits, baseline the newest files first, record a warning, and avoid unbounded
  state growth. The implementation commit must choose concrete defaults for file
  count, bytes read per refresh, oversized-line handling, and cursor pruning.

## CLI

- `codex-pm start --repo <path>`: observes Codex sessions by default.
- `codex-pm watch --repo <path>`: same observer behavior as `start`.
- `codex-pm start --repo <path> [--sessions-dir <path>]`: run the sidecar
  against an alternate sessions directory, primarily for tests and debugging.
- `codex-pm watch --repo <path> [--sessions-dir <path>]`: same sessions-dir
  override as `start`.
- `codex-pm observe --repo <path> [--sessions-dir <path>] [--from-start]
  [--since <timestamp>]`: one-shot observer ingestion. Without `--from-start`
  or `--since`, it follows the same privacy-safe EOF policy as `start`.
- `--since` accepts an RFC 3339 timestamp with timezone. Invalid or timezone-less
  timestamps fail closed with an error and no ingestion. During `--since`
  backfill, records with missing, invalid, or timezone-less timestamps are
  skipped and do not advance the backfill inclusion boundary. Valid pre-since
  `session_meta` and `turn_context` records may be parsed metadata-only to build
  effective cwd context, but they are never ingested as observed activity.
  Malformed context records invalidate effective cwd until the next valid
  context record. Content records with missing or invalid timestamps fail closed
  for that record: they do not ingest content and do not create advisories from
  raw content.
- `codex-pm start --no-observe-codex` and
  `codex-pm watch --no-observe-codex`: disable session observation for the
  sidecar when needed. The opt-out must suppress session discovery, EOF
  baselining, ingestion, observer state writes, and observer-generated
  advisories.
- Update `README.md` and `AGENTS.md` with the new observer flags and the
  privacy-safe default behavior in the same commit as the observer code.

## Tests

- Unit tests for:
  - record-level cwd scoping from `session_meta.cwd` and `turn_context.cwd`,
    including mixed-cwd sessions, repo subdirectories, symlink-resolved paths,
    and sibling-prefix false positives
  - fail-closed cwd validation for missing, non-string, empty, relative,
    shell-expanded, user-expanded, and unresolvable cwd values
  - `--since` cwd scoping with valid pre-since context records, malformed
    context records, missing content timestamps, invalid content timestamps, and
    schema-drift records
  - JSONL event classification for prompts, assistant responses, tool calls, and
    outputs
  - `response_item` envelope parsing and unknown-record/schema-drift ignores
  - shell command extraction from tool/function call arguments
  - offset tracking, idempotent re-runs, persisted EOF default policy, explicit
    `--from-start` backfill, RFC 3339 `--since` boundaries and invalid timestamp
    failure, newly discovered file EOF baselining, preexisting file append after
    sidecar baseline, restart behavior, partial-line retry, file truncation,
    file rotation, replacement, separate backfill cursors, copied or touched
    historical file EOF baselining, and dedupe keys
  - malformed line handling and repeated parse-failure warning thresholds
- Integration tests for:
  - replacing the current placeholder `observe` tests so `observe` exits
    successfully when ingestion succeeds
  - `observe --sessions-dir` ingesting synthetic session files
  - unrelated repository sessions being ignored
  - observer-generated advisories from prompts, assistant responses, tool calls,
    shell commands, and command outputs
  - read-only observation preserving synthetic session file contents and mtimes
  - full, partial-prefix, and secret-like raw observed sentinel content absent
    from every `.codex-pm/state.json` field, including transcripts, observer
    metadata, activity summaries/details, advisory messages, advisory source
    summaries, and advisory reasons
  - secret-like sentinel values in executable paths and tool ids being redacted
  - symlink and non-regular session-file candidates being ignored
  - unreadable files and sessions-tree file/byte limits recording warnings
  - README/AGENTS documented observer commands matching CLI help
- E2e tests for:
  - `start --no-observe-codex` and `watch --no-observe-codex` suppressing
    discovery, EOF baselining, ingestion, observer state writes, and observer
    advisories
  - two-run `start --once --sessions-dir <synthetic>` flow: first establish the
    sidecar baseline, then append a new active session record and verify status
    updates while preserving the one-command sidecar workflow
  - preexisting synthetic session with historical records plus a post-baseline
    append only ingests the appended record by default
  - explicit `observe --from-start --sessions-dir <synthetic>` backfill of an
    existing synthetic session
  - any session file first discovered by default live observation is baselined at
    EOF and not read from byte 0, including newly created, copied, touched,
    replaced, or rotated files
  - repeated observer runs not duplicating transcripts or bumping state revision
    when no new records exist
  - interrupt-level advisories from observed prompts, assistant responses, tool
    calls, shell commands, and command outputs rendering in status
