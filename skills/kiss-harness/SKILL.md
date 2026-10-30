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
   decision with the owner: `grilling` when installed, else the rounds in
   [references/spec-and-tickets.md](references/spec-and-tickets.md). Write each settled answer into `R/decisions.md`
   at once. With domain docs on, also use `domain-modeling`. Then write `R/spec.md` from `templates/spec.md` by the
   spec rules in that file, and confirm the test seams with the owner.
2. **Tickets** in `R/tickets.json`: a list of `{id, title, spec, acceptance: [...], passes: false}`, and optional
   `files`, `symbols`, `seeds` (CodeGraph queries), `depends_on`, `risky`. Follow the ticket rules in
   [references/spec-and-tickets.md](references/spec-and-tickets.md): tracer bullets, a refactor first, blocking
   links, a wide refactor in three stages, and an acceptance line that names its seam. A ticket with a time window
   (freshness, a timeout, staleness) asks for a test that runs the clock past that window. Mark the safety rule, the
   guard whose failure harms real data, `risky`. Then `tickets.py check R`, and a ponytail pass at **full** level
   (cut each line that no person asked for, and record the cut in `decisions.md`). Ask the owner about the
   breakdown, change it until the owner says yes (that yes also confirms the seams), then `tickets.py render R`.
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
   BLOCKED: `tickets.py continue R <elapsed> <budget>` → send it to the SAME implementer. After 3 continuations, or
   on BLOCKED, the owner decides.
6. **A risky ticket** is reviewed alone as soon as the implementer names it (step 7 on its commits), before the
   rest of the build depends on it.
7. **Review once at the end:** `prompt.py reviewer ... HEAD=<head> APP="<how to start the product, and its test
   data>"` → a NEW subagent on your strongest model. It uses the product, loads `ponytail-review` for rubric G, and
   reports every issue it finds.
8. **Sort:** `prompt.py severity ... FINDINGS=@<findings file>` (a subagent, or you): fix, owner or log. Ask the
   owner the owner questions.
9. **Fix rounds:** `prompt.py fix ... ROUND=<n> FINDINGS=@<fix list>` → the SAME implementer; then
   `prompt.py recheck ... ROUND=<n> FIX_BASE=<sha> FIX_HEAD=<sha> ANSWER=@<its answer>` → the SAME reviewer.
   At most 3 rounds; then the owner decides.
10. **Close:** the project's full check once (the facts file names it). Then `ponytail-debt` on the run's changes
    (`git -C W diff <base>..<head>`): the report lists each new `shortcut:` comment with its limit. Then the
    docs, and the merge on the owner's yes. Never push, open a pull request or write to a remote without the owner's
    explicit go.

**The clock:** no agent gives a subagent a time budget, so put "Time: elapsed Ns of a Ms budget." in each message
(`prompt.py` does it when you pass `ELAPSED`). Past the budget, stop and ask the owner before the next round.

## Rules

- Findings go back to the agent that has the context: fixes to the same implementer, rechecks to the same reviewer.
  When your agent cannot reach a finished subagent again, start a new one with the same prompt plus "Read
  `R/progress.md` first: it is the handoff".
- One commit per ticket, files added by explicit path, never `git add -A`.
- Read a subagent's report as a claim: check its JSON against `git`, `tickets.py check` and the files.
- The owner's word decides every open question, every merge and every push.

## Traps

Read [references/traps.md](references/traps.md) once, before step 3. The implementer and reviewer prompts name it
too, so every agent of the run reads the same traps.
