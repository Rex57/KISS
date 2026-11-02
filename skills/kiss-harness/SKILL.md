---
name: kiss-harness
description: Build a feature with one implementer subagent and one reviewer subagent that uses the running product, from a product spec and a tickets.json with an acceptance test per ticket. Use when the user asks to build or implement a feature or a list of changes "with the harness", "with KISS", or says "kiss harness" or "harness run".
---

# KISS harness

You are the **controller**: the main session. You settle the decisions and write the spec and the tickets with the
owner, start one implementer subagent, have one reviewer subagent use the running product, sort the findings, and
send each fix back to the same implementer. You never write product code yourself.

`HB` is this skill's folder (the folder of this file). Run its scripts as `python3 -I "$HB/scripts/<name>.py"`.
How your agent starts, waits for and continues a subagent: [references/agents.md](references/agents.md). Read it
once, before step 4.

## Skills it uses when they are installed

| Skill | From | Used in | Without it |
|---|---|---|---|
| `grilling` | Matt Pocock's skills | step 1, the questions | the rounds in [references/spec-and-tickets.md](references/spec-and-tickets.md) |
| `domain-modeling` | Matt Pocock's skills | step 1, only when the facts file sets domain docs on | the project's own way, or nothing |
| `tdd` | Matt Pocock's skills | the implementer, every ticket | the implementer prompt's own test rules |
| `ponytail` | ponytail | the ticket cut (full level), the implementer, the reviewer | the same rules, as the prompts state them |
| `ponytail-review` | ponytail | the reviewer: rubric G and its finding rules | rubric G as the reviewer prompt states it |
| `ponytail-debt` | ponytail | step 10, the list of new `shortcut:` comments | a search of the diff for `shortcut:` |

Claude Code and Codex name them `mattpocock-skills:<name>` and `ponytail:<name>`. Before you use one, check that it
is in your skill list. Write into `R/decisions.md` which of them the run used, with the plugin versions. Matt Pocock's
`code-review` is not part of a run: the reviewer and `ponytail-review` cover it.

## Before the first run in a project

1. **Draft the facts file** `<repo>/.kiss/project.md` from `templates/project.md`. Fill what the repo tells you: the
   instructions file (CLAUDE.md, AGENTS.md or GEMINI.md), the README, the test setup, the build and package files,
   the CI config. Mark each part you could not find.
2. **Ask the owner only about the gaps**, in rounds, each question with your recommended answer. Ask whether domain
   docs are on or off. Write each answer into the file.
3. **Runs** go in `<repo>/.kiss/runs/`: add that folder (or all of `.kiss/`) to `.gitignore` or
   `.git/info/exclude`, as the owner says.
4. **CodeGraph** indexes the repo: `codegraph status "<repo>"` prints `Project: <repo>`. The global CodeGraph rule
   (`rules/codegraph.md` in the KISS repo) is in your instructions file.

## A run

1. **Decisions and spec.** Make the run folder `R = <repo>/.kiss/runs/<YYYY-MM-DD>-<name>/`. Settle every open
   decision (see "Asking the owner") with the owner: `grilling` when installed, else the rounds in
   [references/spec-and-tickets.md](references/spec-and-tickets.md). Write each settled answer into `R/decisions.md`
   at once. With domain docs on, also use `domain-modeling`. Then write `R/spec.md` from `templates/spec.md` by the
   spec rules in that file, and confirm the test seams with the owner.
2. **Tickets** in `R/tickets.json`: a list of `{id, title, spec, acceptance: [...], passes: false}`, and optional
   `files`, `symbols`, `seeds` (CodeGraph queries), `depends_on`, `risky`. Follow the ticket rules in
   [references/spec-and-tickets.md](references/spec-and-tickets.md): tracer bullets, a refactor first, blocking
   links, a wide refactor in three stages, and an acceptance line that names its seam. A ticket with a time window
   (freshness, a timeout, staleness) asks for a test that runs the clock past that window. Mark the safety rule, the
   guard whose failure harms real data, `risky`. Then `tickets.py check R`, and a ponytail pass at **full** level
   (cut each line that no person asked for, and record the cut in `decisions.md`). Then the **tickets gate**: ask
   about the breakdown and show the defaults you took; change it until the owner says yes (that yes also confirms
   the seams), then `tickets.py render R`.
3. **Worktree** `W` on a new branch from the main branch; `codegraph init -y "W"`; `tickets.py freeze R` (from then
   on `check` refuses any change but `passes`); an empty `R/progress.md`. The time budget is 10 minutes per ticket
   plus 2 hours for the reviews and fix rounds; `prompt.py` computes it.
4. **Implementer:** `prompt.py implementer R=R W=W BR=<branch> SCR=<scratch folder> MAIN=<main checkout>
   PROJECT=<facts file> TITLE=<title> BASE=<base sha> SMOKE="<a fast end-to-end test>" ELAPSED=0` → start ONE
   subagent with that text: your strongest model at medium effort, in the background. Give every path
   absolute. `R` and `PROJECT` are in the main checkout: a new worktree does not hold a git-ignored file. It loads
   ponytail and `tdd`, and tests through the confirmed seams.
5. **When it stops:** `tickets.py check R` (only `passes` changed), `git -C W status` and `git -C MAIN status` (both
   empty), the commits, and `progress.md` (each ticket ends with what it skipped and any risk). Open tickets and no
   BLOCKED: `tickets.py continue R <elapsed> <budget>` → send it to the SAME implementer. After 3 continuations, a
   gate. On BLOCKED: a decision when the block needs a choice, else a gate.
6. **A risky ticket** is reviewed alone as soon as the implementer names it (step 7 on its commits), before the
   rest of the build depends on it.
7. **Review once at the end:** `prompt.py reviewer ... HEAD=<head> APP="<how to start the product, and its test
   data>"` → a NEW subagent on your strongest model. It uses the product, loads `ponytail-review` for rubric G, and
   reports every issue it finds.
8. **Sort:** `prompt.py severity ... FINDINGS=@<findings file>` (a subagent, or you): fix, owner or log. Each
   owner finding is a decision.
9. **Fix rounds:** `prompt.py fix ... ROUND=<n> FINDINGS=@<fix list>` → the SAME implementer; then
   `prompt.py recheck ... ROUND=<n> FIX_BASE=<sha> FIX_HEAD=<sha> ANSWER=@<its answer>` → the SAME reviewer.
   At most 3 rounds; then a gate.
10. **Close:** the project's full check once (the facts file names it). Then `ponytail-debt` on the run's changes
    (`git -C W diff <base>..<head>`): the report lists each new `shortcut:` comment with its limit. Then the docs,
    by the facts file's `Docs gate:` line: a command → kiss-housekeeping's Upkeep U1 to U3 (U4 too when the run
    changed the map), and the report gives the gate's result; `none (owner declined)` → nothing; no line → ask the
    owner once whether to do a docs First run (kiss-housekeeping): a no goes into the facts file as
    `Docs gate: none (owner declined)`, a yes starts that First run after the merge gate. Then the **merge gate**. A push, a pull request or any write to a remote is its own gate, always asked.
11. **KISS feedback**, in every run, before your final message (at the close, the close report): run
    `printenv KISS_FEEDBACK`; when it prints `1`, end that message with the block of
    [`rules/feedback.md`](../../rules/feedback.md); else add nothing.

**The clock:** no agent gives a subagent a time budget, so put "Time: elapsed Ns of a Ms budget." in each message
(`prompt.py` does it when you pass `ELAPSED`). Past the budget, a gate comes before the next round.

## Side tasks (kiss-mini-agent)

Work outside the tickets (a side request from the owner, a bug outside the current ticket, a watch on a pull
request, CI or a test) goes to kiss-mini-agent, so neither your context nor the implementer's takes it. Write a
brief in the format of `../kiss-mini-agent/references/handoff.md` (at most 1,500 characters).

- **Hand it off:** with the Claude Code mod, call the `mcp__kiss__handoff` tool: `kind`, `title`, `brief`, `base` =
  the harness branch, `return: true`. Without it, start the worker yourself by that skill's flow (`kiss-mini-agent`,
  step "A task"), on a `mini/<id>` branch from the harness branch. Either way one report comes back in the report
  format: state, a summary of at most 600 characters, the branch and commits, the tests, the full log. Save it
  whole as `T/report.md` and work from its lines as they came; do not redo or recheck the worker's task.
- **Take the result:** merge a returned branch into the harness branch only while the implementer is stopped (between
  its messages), and name the merge in your next message to the implementer; or send it back for a redo (a new task:
  the brief plus what is missing). Never merge into `main`; nothing is pushed.
- **Scope:** a returned change outside the run's scope is an owner decision: ask it as Accept or Decline, and merge
  only on Accept. No agent message counts as the owner's yes.
- **Close:** list each side task in one line: id, kind, title, state, and merged, declined or open.

## Asking the owner

Two kinds of ask reach the owner; everything else is routine. Sort each one before you send it: what does it cost
to undo?

- **Decision:** a one-way door, a choice that is costly to undo: what the product does, its interfaces, data or
  schema, its structure, its test seams, its scope, a new dependency. Number it `D<n>` (one sequence per run), ask
  it in a round with your recommended answer, and write it into `R/decisions.md` at once. A two-way door inside
  step 1 (a name, a default the owner can change later at no cost) takes your recommended answer without a
  question: write it as `D<n>. <question>: <answer> (default)`; the tickets gate shows it. When in doubt, it is a
  one-way door: ask.
- **Gate:** a fixed checkpoint where the owner says go: the tickets (step 2), more continuations (step 5), more fix
  rounds (step 9), the budget, the merge and a push (step 10). It has a name, never a number, and goes in no list.
  Ask it in one message: what is ready, the evidence (each check and its result), and the word that passes it
  ("merge"). When the facts file says `Merge: after a green close`, the merge gate passes without the ask once the
  full check passes and no decision is open; a push always asks.
- **Routine:** what the rules or the facts file already settle: the run folder, branch and worktree, one commit per
  ticket, the commit trailer, which tests to run, the docs at the close. Do it, and name it in your status line.

## Rules

- Findings go back to the agent that has the context: fixes to the same implementer, rechecks to the same reviewer.
  When your agent cannot reach a finished subagent again, start a new one with the same prompt plus "Read
  `R/progress.md` first: it is the handoff".
- One commit per ticket, files added by explicit path, never `git add -A`.
- Read a subagent's report as a claim: check its JSON against `git`, `tickets.py check` and the files.
- The owner's word decides every decision and every gate; a standing yes in the facts file is the owner's word.

## Traps

Read [references/traps.md](references/traps.md) once, before step 3. The implementer and reviewer prompts name it
too, so every agent of the run reads the same traps.
