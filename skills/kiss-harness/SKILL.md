---
name: kiss-harness
description: Build a feature with one implementer subagent and one reviewer subagent that uses the running product, from a product spec and a tickets.json with an acceptance test per ticket. Use when the user asks to build or implement a feature or a list of changes "with the harness", "with KISS", or says "kiss harness" or "harness run".
---

# KISS harness

You are the **controller**: the main session. You write the spec and the tickets with the owner, start one
implementer subagent, have one reviewer subagent use the running product, sort the findings, and send each fix
back to the same implementer. You never write product code yourself.

`HB` is this skill's folder (the folder of this file). Run its scripts as `python3 -I "$HB/scripts/<name>.py"`.
How your agent starts, waits for and continues a subagent: [references/agents.md](references/agents.md). Read it
once, before step 4.

## Before the first run in a project

- **The project facts file** `<repo>/.kiss/project.md`: copy `templates/project.md` and fill it in with the owner.
  It says how to run, test and start the product, the rules a reviewer checks and the traps. Every run reads it.
- **Runs** go in `<repo>/.kiss/runs/`: add that folder to `.gitignore` or `.git/info/exclude`.
- **CodeGraph** indexes the repo: `codegraph status "<repo>"` prints `Project: <repo>`. The global CodeGraph rule
  (`rules/codegraph.md` in the KISS repo) is in your instructions file.

## A run

1. **Run folder** `R = <repo>/.kiss/runs/<YYYY-MM-DD>-<name>/` with `spec.md` (from `templates/spec.md`: what a
   person can do and why) and `decisions.md` (the owner's rulings and the run defaults). Ask the owner each
   question the spec leaves open, and record each answer in `decisions.md`.
2. **Tickets** in `R/tickets.json`: a list of `{id, title, spec, acceptance: [...], passes: false}`, and optional
   `files`, `symbols`, `seeds` (CodeGraph queries), `depends_on`, `risky`. Each acceptance line is a check that a
   person or a test can run. A ticket with a time window (freshness, a timeout, staleness) asks for a test that runs
   the clock past that window. Mark the safety rule, the guard whose failure harms real data, `risky`.
   Then `tickets.py check R`, a ponytail pass (cut each line that no person asked for, and record the cut in
   `decisions.md`), and `tickets.py render R`. Show the owner the list and wait for a yes.
3. **Worktree** `W` on a new branch from the main branch; `codegraph init -y "W"`; `tickets.py freeze R` (from then
   on `check` refuses any change but `passes`); an empty `R/progress.md`. The time budget is 10 minutes per ticket
   plus 2 hours for the reviews and fix rounds; `prompt.py` computes it.
4. **Implementer:** `prompt.py implementer R=R W=W BR=<branch> SCR=<scratch folder> MAIN=<main checkout>
   PROJECT=<facts file> TITLE=<title> BASE=<base sha> SMOKE="<a fast end-to-end test>" ELAPSED=0` → start ONE
   subagent with that text: your strongest model at medium effort, in the background.
5. **When it stops:** `tickets.py check R` (only `passes` changed), `git -C W status` and `git -C MAIN status` (both
   empty), the commits, and `progress.md`. Open tickets and no BLOCKED: `tickets.py continue R <elapsed> <budget>`
   → send it to the SAME implementer. After 3 continuations, or on BLOCKED, the owner decides.
6. **A risky ticket** is reviewed alone as soon as the implementer names it (step 7 on its commits), before the
   rest of the build depends on it.
7. **Review once at the end:** `prompt.py reviewer ... HEAD=<head> APP="<how to start the product, and its test
   data>"` → a NEW subagent on your strongest model. It uses the product and reports every issue it finds.
8. **Sort:** `prompt.py severity ... FINDINGS=@<findings file>` (a subagent, or you): fix, owner or log. Ask the
   owner the owner questions.
9. **Fix rounds:** `prompt.py fix ... ROUND=<n> FINDINGS=@<fix list>` → the SAME implementer; then
   `prompt.py recheck ... ROUND=<n> FIX_BASE=<sha> FIX_HEAD=<sha> ANSWER=@<its answer>` → the SAME reviewer.
   At most 3 rounds; then the owner decides.
10. **Close:** the project's full check once (the facts file names it), the docs, then merge on the owner's yes.
    Never push, open a pull request or write to a remote without the owner's explicit go.

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

- Use absolute paths in every command: a shell that resets its folder has built in the main checkout before.
- zsh: write heredocs as `<<'EOF'` (an unquoted one runs every backtick); zsh does not split an unquoted `$VAR`
  into words; macOS has no `timeout`.
- A test that reads the clock twice flakes at a second boundary: read it once per stamp.
- A worktree has no CodeGraph watcher: `codegraph sync -q "W"` after each commit.
- A tool result that shows a preview and names a file: read the file before you act.
