# Repository Guidelines

## Project Structure & Module Organization

This repository currently captures the product direction for `codex-pm` rather
than implementation code. `README.md` is the canonical project brief, and
`.gitignore` is present but currently empty. Keep top-level documentation short
and task oriented. When implementation begins, prefer `src/` for runtime code,
`tests/` for automated tests, `docs/` for longer design notes, and `assets/`
for static images or fixtures. Do not commit generated files unless they are
required for the project to run or be reviewed.

## Build, Test, and Development Commands

No package manager, build system, or test runner is committed yet. Until one is
added, use repository-level checks:

- `rg --files`: confirm expected files are present and visible.
- `git diff --check`: catch trailing whitespace and patch formatting issues.
- `git status --short`: review modified and untracked files before handoff.

When adding tooling, document the exact commands in `README.md` and update this
file, for example `npm test`, `python -m pytest`, or `cargo test`.

## Coding Style & Naming Conventions

Markdown is the primary format today. Use sentence-case headings, concise
paragraphs, and hyphen bullets. Wrap commands, paths, and filenames in
backticks. Prefer lowercase, hyphenated filenames for docs such as
`design-notes.md`, unless a conventional uppercase file is expected
(`README.md`, `AGENTS.md`). For future source code, follow the formatter and
lint rules of the chosen language, and commit the relevant config with the code.

## Testing Guidelines

There are no automated tests yet. For documentation-only changes, verify
rendering, spelling, and `git diff --check`. When implementation starts, add
tests beside the feature or under `tests/`, use clear behavior-focused names,
and make sure the primary test command runs from the repository root.

## Commit & Pull Request Guidelines

Recent commits use short imperative summaries with a trailing period, such as
`Add README.md.` and `Update README.md.` Follow that style unless the project
adopts a stricter convention. Pull requests should include a concise summary,
the motivation for the change, any validation performed, and linked issues or
follow-up tasks when relevant. Include screenshots or terminal output only when
they clarify user-visible behavior.
