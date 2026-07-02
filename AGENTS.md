# Repository Guidelines

## Project Structure & Module Organization

This repository contains the product direction and the initial Python
implementation for `codex-pm`. `README.md` is the canonical project brief.
Runtime code lives in `src/codex_pm/`, tests live in `tests/`, and longer design
or planning notes live in `docs/`. Keep top-level documentation short and task
oriented. Do not commit generated files unless they are required for the project
to run or be reviewed.

## Build, Test, and Development Commands

The implementation currently uses Python 3 standard-library code and
`unittest`. Use repository-level checks:

- `rg --files`: confirm expected files are present and visible.
- `git diff --check`: catch trailing whitespace and patch formatting issues.
- `git status --short`: review modified and untracked files before handoff.

Current commands:

- `./codex-pm start --repo .`: start the sidecar loop for this repository.
- `./codex-pm start --repo . --once`: run one sidecar refresh and exit.
- `./codex-pm init --repo .`: initialize durable local state.
- `./codex-pm status --repo .`: print the current project status once.
- `python3 -m unittest discover`: run all tests.
- `python3 -m unittest discover tests/unit`: run unit tests.
- `python3 -m unittest discover tests/integration`: run integration tests.
- `python3 -m unittest discover tests/e2e`: run e2e tests.
- `git diff --check`: catch trailing whitespace and patch formatting issues.
- `rg --files`: confirm expected files are present and visible.
- `git status --short`: review modified and untracked files before handoff.

When adding or changing tooling, document the exact commands in `README.md` and
update this file.

## Coding Style & Naming Conventions

Markdown is the primary format today. Use sentence-case headings, concise
paragraphs, and hyphen bullets. Wrap commands, paths, and filenames in
backticks. Prefer lowercase, hyphenated filenames for docs such as
`design-notes.md`, unless a conventional uppercase file is expected
(`README.md`, `AGENTS.md`). For future source code, follow the formatter and
lint rules of the chosen language, and commit the relevant config with the code.

## Testing Guidelines

Automated tests use `unittest` and live under `tests/`. For documentation-only
changes, verify rendering, spelling, and `git diff --check`. For code changes,
add focused tests beside the relevant behavior under `tests/unit`,
`tests/integration`, or `tests/e2e`, and make sure `python3 -m unittest
discover` runs from the repository root.

## Commit & Pull Request Guidelines

Recent commits use short imperative summaries with a trailing period, such as
`Add README.md.` and `Update README.md.` Follow that style unless the project
adopts a stricter convention. Pull requests should include a concise summary,
the motivation for the change, any validation performed, and linked issues or
follow-up tasks when relevant. Include screenshots or terminal output only when
they clarify user-visible behavior.
