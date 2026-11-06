# <Project>: run, test, rules, traps (KISS harness)

The controller drafts this file at `<repo>/.kiss/project.md` before the first run (SKILL.md, "Before the first
run"), and the owner fills the gaps. Every implementer and reviewer reads it once. Keep it short: leave out what the
project's instructions file (CLAUDE.md, AGENTS.md or GEMINI.md) already says.

## Run

- The environment to set, and to unset, in a fresh shell.
- One test file: `<command>`. One group: `<command>`.
- Tests `codegraph affected` cannot see: a script's own `--selftest`, tests that load the code without an import (a
  mod's tests), and the command for each.
- Smoke check (one fast end-to-end test, run before any new work): `<command>`.
- The full check (the controller runs it at the close, at the head that merges): `<command>`.
- Full check time: <n> minutes (how long the full check runs; the run's time budget adds it once).
- Flake check: `<command> x <n>` (the tests to run n times in a row in the background beside the final review, when
  the run's tests add a time value; a failure, or a time bound under 2 times the slowest time seen, is a fix).
- Shared test resources: what the tests and the full check start (a database, a server, the app), its memory or
  connection limit, and how many agents or sessions may use it at once ("one at a time" holds the implementer's
  product checks while a solo reviewer uses it).
- Build steps: which change needs which build, and what goes in the same commit (for example: a change under
  `web/` ends with `npm run build`, and the built files go in the same commit).
- Commit trailer: the exact lines each commit message ends with, or "none".
- Merge: `ask` (the merge gate asks the owner) or `after a green close` (a standing yes: merge when the full check
  passes and no decision is open). A push always asks.
- After merge: `ask` (a commit after the owner's "merge" asks again) or `same go for tests and docs` (the owner's
  "merge" also covers a later commit that changes only tests, docs or built files).
- Docs gate: `python3 -I tools/check_docs.py .` (a kiss-housekeeping First run installs it; the close runs its
  Upkeep), or `none (owner declined)`. With no line, the close asks once.

## Start the product for a reviewer

- How to start a scratch copy: a free port, a scratch store, never a live one.
- The test accounts, and how to sign in.
- How to drive the UI (a headless browser) and the API, and the test data to load.
- GUI: how an agent drives only its own copy of the app (its own build, window and data), never the owner's
  running app.

## Domain docs

- on | off. On: a term that needs a fixed meaning goes in `GLOSSARY.md`, and a decision that is hard to reverse
  becomes an ADR in `docs/adr/` (the `domain-modeling` skill). Off: name where the project keeps its lasting
  decisions instead, if anywhere.

## Rules a reviewer checks (rubric C)

- <the rule> (<the file that enforces it>), one line each.

## Traps

- <the trap, and what to do instead>, one line each: only the ones that cost a run time.
