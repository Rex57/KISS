# <Project>: run, test, rules, traps (KISS harness)

Copy this file to `<repo>/.kiss/project.md` and fill it in with the owner before the first run. Every
implementer and reviewer reads it once. Keep it short: leave out what the project's instructions file
(CLAUDE.md, AGENTS.md or GEMINI.md) already says.

## Run

- The environment to set, and to unset, in a fresh shell.
- One test file: `<command>`. One group: `<command>`.
- The full check (the controller runs it once, at the end): `<command>`.
- Build steps: which change needs which build, and what goes in the same commit (for example: a change under
  `web/` ends with `npm run build`, and the built files go in the same commit).

## Start the product for a reviewer

- How to start a scratch copy: a free port, a scratch store, never a live one.
- The test accounts, and how to sign in.
- How to drive the UI (a headless browser) and the API, and the test data to load.

## Rules a reviewer checks (rubric C)

- <the rule> (<the file that enforces it>), one line each.

## Traps

- <the trap, and what to do instead>, one line each: only the ones that cost a run time.
