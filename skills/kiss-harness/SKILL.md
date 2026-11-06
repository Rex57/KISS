---
name: kiss-harness
description: Build a feature from a spec and tickets with one implementer subagent and one reviewer that uses the running product. Use when the user asks to build a feature or a list of changes "with the harness" or "with KISS", or says "kiss harness" or "harness run".
allowed-tools: Bash(python3 -I "${CLAUDE_PLUGIN_ROOT}/rules/feedback.py" *)
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
| `codebase-design` | Matt Pocock's skills | step 1, when the run adds or changes a module's interface or a seam: its words (module, interface, seam, depth) and its deepening check | the spec in plain words, with no deepening check |
| `prototype` | Matt Pocock's skills | step 1, a decision that needs an answer the owner can try (a state model, a UI): a throwaway prototype, never merged into the main branch | the question in words only |
| `tdd` | Matt Pocock's skills | the implementer, every ticket | the implementer prompt's own test rules |
| `diagnosing-bugs` | Matt Pocock's skills | the implementer, a failure it cannot explain | the implementer's own debugging |
| `pr` | Matt Pocock's skills | step 10, the push gate: the body of a pull request the owner asks for | a body with the run's summary, tickets and tests |
| `ponytail` | ponytail | the ticket cut (full level), the implementer, the reviewer | the same rules, as the prompts state them |
| `ponytail-review` | ponytail | the reviewer: rubric G and its finding rules | rubric G as the reviewer prompt states it |
| `ponytail-debt` | ponytail | step 10, the list of new `shortcut:` comments | a search of the diff for `shortcut:` |

Claude Code and Codex name them `mattpocock-skills:<name>` and `ponytail:<name>`. Before you use one, check that it
is in your skill list; a skill that is not there is skipped, and the step does what the "Without it" column says. Step 3 writes which of them the run uses, with their plugin versions, on the first line of `R/progress.md`. Matt Pocock's
`code-review` is not part of a run: the reviewer and `ponytail-review` cover it.

## Before the first run in a project

1. **Draft the facts file** `<repo>/.kiss/project.md` from `templates/project.md`. Fill what the repo tells you: the
   instructions file (CLAUDE.md, AGENTS.md or GEMINI.md), the README, the test setup, the build and package files,
   the CI config. Mark each part you could not find.
2. **Ask the owner only about the gaps**, in rounds, each question with your recommended answer. Ask whether domain
   docs are on or off. Write each answer into the file.
3. **Runs** go in `<repo>/.kiss/runs/` and their worktrees in `<repo>/.kiss/worktrees/`: add both folders (or all
   of `.kiss/`) to `.gitignore` or `.git/info/exclude`, as the owner says.
4. **CodeGraph** indexes the repo: `codegraph status "<repo>"` prints `Project: <repo>`. The global CodeGraph rule
   (`rules/codegraph.md` in the KISS repo) is in your instructions file.

## A run

1. **Decisions and spec.** Make the run folder `R = <repo>/.kiss/runs/<YYYY-MM-DD>-<name>/`. First, `grep -l "Look
   back: open" <repo>/.kiss/runs/*/decisions.md`: ask each line under that heading as a yes/no before anything else,
   and move each answered line to `## Look back: answered` in its file. For a run brief of a
   kiss-system-design run plan, read the brief and the design document first and ask only what they leave open; a
   design decision the run finds wrong goes back to the owner (`kiss-system-design <name>`, its loop back). Settle
   every open decision with the owner ("Asking the owner"): call the Skill tool with `mattpocock-skills:grilling`
   when installed, also when the owner's answers are given, else the rounds in
   [references/spec-and-tickets.md](references/spec-and-tickets.md). With domain docs on, also use
   `domain-modeling`. When the run adds or changes a module's interface or a seam, call the Skill tool with
   `mattpocock-skills:codebase-design` before you write the spec, and use its words and its deepening check. A
   decision the owner must try first (a state model, a UI) gets a throwaway `prototype` (scratch folder, or a branch
   never merged). A decision that rests on a runtime fact of an early-access API (where a spawned agent's shell
   starts, what a hook sees) gets your live spike of that fact in a scratch folder, before the tickets gate: a fact
   is yours to check, not the owner's to try. The **test seams** are one decision `D<n>`: each seam with what it
   catches and misses, asked once. Then write `R/spec.md` from `templates/spec.md` by the spec rules in that file.
2. **Tickets** in `R/tickets.json`: a list of `{id, title, spec, acceptance: [...], passes: false}`, and optional
   `files`, `symbols`, `seeds` (CodeGraph queries), `depends_on`, `risky`. Follow the ticket rules in
   [references/spec-and-tickets.md](references/spec-and-tickets.md): tracer bullets, a refactor first, blocking
   links, a wide refactor in three stages, an acceptance line that names its seam, and the failure-path lines. A ticket with a time window
   (freshness, a timeout, staleness) asks for a test that runs the clock past that window. Mark a ticket `risky` only
   when it is a guard whose failure harms real data, or a guard that later tickets build on. Then `tickets.py check
   R`, and a ponytail pass at **full** level: call the Skill tool with `ponytail` at full level for the cut; without
   it, the rule as stated here: cut each line that no person asked for, and record the cut in `decisions.md`. Then the **tickets gate**: ask about the breakdown and show the defaults you took; change it until
   the owner says yes, then `tickets.py render R`.
3. **Worktree** `W = <repo>/.kiss/worktrees/<run>/` (git-ignored; never a session scratch folder, which a session
   restart can delete) on a new branch from the main branch; `codegraph init -y "W"`; `tickets.py freeze R` (from then
   on `check` refuses any change but `passes`); `R/progress.md` with one line: the skills of the table above that the
   run uses and their plugin versions (the version folder in each skill's base path).
4. **Implementer:** write the run's values once: `prompt.py start R W=W BR=<branch> SCR=<scratch folder>
   MAIN=<main checkout> PROJECT=<facts file> TITLE=<title> BASE=<base sha> SMOKE="<a fast end-to-end test>"
   APP="<how to start the product, and its test data>"` (R/run.json, with the running KISS `VERSION`). Show the owner
   each WARN it prints for a facts line the file lacks, before the build. Any `prompt.py` call that prints "KISS <new>
   is installed" on stderr: tell the owner to start the run in a new session. Then `prompt.py implementer R ELAPSED=0` →
   start ONE subagent with that text: your strongest model at medium effort, in the background. Give every path
   absolute. `R` and `PROJECT` are in the main checkout: a new worktree does not hold a git-ignored file.
5. **When it stops:** `tickets.py check R` (only `passes` changed), `git -C W status` and `git -C MAIN status` (both
   empty), the commits, and `progress.md` (each ticket ends with what it skipped and any risk). **Triage** each new
   `Skipped:` and `Risk:` line into one of three buckets: fix now (in the continue message), owner (a decision,
   asked at once) or log; write each line and its bucket into the "Triage" part of `R/decisions.md`. Run `callcheck.py -p
   W <the HEAD at the last stop, or BASE at the first>..HEAD` and send each caller line it prints to read to the implementer. Open tickets and no
   BLOCKED: `tickets.py continue R <elapsed> <budget>` → send it to the SAME implementer (after a risky ticket,
   step 6's `--review` message goes instead). Before each continue, fix
   round and recheck, run `metrics.py R --context` (Claude Code): an agent it marks gets the handoff of
   [references/agents.md](references/agents.md) instead, and the round goes to the new one. After 3 continuations, a
   gate. On BLOCKED: a decision when the block needs a choice, else a gate.
6. **A risky ticket** is reviewed alone (step 7 on its commits) as soon as the implementer names it; otherwise the
   final review covers it. Start the solo reviewer, and at once send the implementer `tickets.py continue R <elapsed>
   <budget> --review <ID>`: only the open tickets that do not depend on the risky one, up to the next risky ticket.
   When it prints nothing (each open ticket waits for it), send no message. The solo review's fix round goes to the
   implementer at its next stop. When the message holds the product checks (the facts file's `Shared test
   resources:` says "one at a time"), send the implementer "product free" as soon as the solo reviewer stops; it then
   runs its held checks.
7. **Review once at the end:** `prompt.py reviewer R HEAD=<head> ELAPSED=<s>` (a risky ticket's review adds
   `BASE=<the commit before it>`) → a NEW subagent on your strongest model at medium effort. Save its last message
   to `R/review-<n>.md` (n = this round's number, from 1). **Flake check:** when the run's test diff (`git -C W diff
   BASE..HEAD` of the test files) adds a time value (a timeout, a sleep, a wall-clock bound), start the facts file's
   `Flake check: <command> x <n>` in the background beside the final review. A failure, or a time bound under 2 times
   the slowest time seen, is a fix before the merge gate.
8. **Sort:** you sort (no subagent) by the rules `prompt.py severity R ROUND=<n>` prints, into `R/sort-<n>.json`,
   then go on. Each owner finding is a decision.
9. **Fix rounds:** write the fix list to `R/fix-<n>.md`; work an owner decision adds after the tickets gate goes in
   it with the ticket rules of [references/spec-and-tickets.md](references/spec-and-tickets.md) (its failure-path
   lines, and a message to an agent checked against that agent's standing prompt). Then `prompt.py fix R ROUND=<n>
   ELAPSED=<s>` → the SAME implementer. Check each test its answer names from the diff and the test output (run the
   test). Save the answer to `R/answer-<n>.md`; when the round fixed a critical, high or reproduced-in-app finding, `prompt.py recheck R
   ROUND=<n> FIX_BASE=<sha> FIX_HEAD=<sha>` → the SAME reviewer (its findings, if any, become `R/review-<n+1>.md`).
   Before each one, the context check of step 5: a marked implementer or reviewer is replaced by the handoff.
   At most 2 fix rounds per review and 3 per run; then a gate. At the cap, when only low or medium findings that
   touch no guard, data or owner rule are left: no gate; run the close, and the merge gate offers them as one
   kiss-mini task. Any other finding left asks a gate.
10. **Close**, in this order, after the last fix round:
    1. The docs, by the facts file's `Docs gate:` line. A command: load kiss-housekeeping and do its Upkeep U1 to U3
       (U4 when the run changed the map), and report the gate's result. `none (owner declined)`: nothing. No line: ask
       the owner once for a docs First run; a no goes into the facts file as `Docs gate: none (owner declined)`
       (committed by explicit path before the merge gate when git tracks that file), a yes starts it after the gate.
    2. **The full check**, yours, at W's HEAD after the docs (the facts file names it). Write `Full check at <sha>:
       <result>` (`pass`, or `fail: <what failed>`) into `R/decisions.md`. A failure is a fix round, then this step again.
    3. `ponytail-debt` on `git -C W diff <base>..<head>`: each new `shortcut:` comment with its limit.
    4. **Look back** by [references/retro.md](references/retro.md): the candidates for the owner, most severe first
       (a mechanical mistake → a proposed check, a judgement call → a facts-file rule), each a yes/no line in the
       merge gate's questions; change no product file.
    5. One **metrics line**: `Metrics: subagents <n>, fix rounds <n>, rechecks <n>, headless sessions <n>, minutes
       <used> of <budget>` (headless sessions: the `claude -p` or `claude --bg` sessions the run starts for tests;
       subagents and kiss-mini workers do not count), given to `python3 -I "$HB/scripts/metrics.py" R --record "<that line>"`: it prints the full
       line (with the tokens per role and the CodeGraph share) and records it in `<repo>/.kiss/runs/metrics.md`, one line
       per run (a rerun of the close replaces the run's line). It refuses when the last `Full check at` line is not a
       pass at W's HEAD.
    6. **Later commits:** `git -C W log --oneline <the full-check sha>..HEAD`. A later commit that changes product
       code gets the full check again (a new `Full check at` line); one that changes only tests, docs or built files
       gets the build step, those tests and the docs gate.
    7. The **merge gate**, with the log findings, the look-back questions, and each later commit with the checks it
       got. A push, a pull request or any write to a remote is its own gate; `pr` writes a pull request's body.
    8. **The merge**, beside the main checkout, never in it (another session may use MAIN):
       1. `git -C MAIN worktree add --detach <tmp> main` (`<tmp>` in the scratch folder), then `git -C <tmp> merge
          --no-ff <branch>`.
       2. When main moved since BASE (`git -C MAIN rev-parse main` is not BASE): run the build step and the checks of
          the files both sides changed (in `git diff --name-only BASE main` and in `git diff --name-only BASE W's
          HEAD`) on the merge result in `<tmp>`. A failure is a gate.
       3. Move main to that tested commit by a fast-forward only: `git -C <the worktree that holds main> merge
          --ff-only <sha>` (`git worktree list` shows it; usually MAIN), or `git -C <tmp> push . HEAD:main` when no
          worktree holds main. A refusal (MAIN's own changes touch the same files) is a gate: never force it.
       4. `git -C MAIN worktree remove <tmp>`. An interrupted merge leaves `<tmp>`: remove it (`git -C MAIN worktree
          remove --force <tmp>`) and build the merge again from 8.1. main moves only by the fast-forward to the tested
          sha, so a failure after that write leaves main on a tested commit.
       5. A commit after the owner's "merge" follows the facts file's `After merge:` line: `ask` (or no line) puts it
          through the merge gate again; `same go for tests and docs` merges a commit that changes only tests, docs or
          built files under the same go once its checks pass, and tells the owner with the undo command (`git -C MAIN
          reset --keep <the main sha before it>`). A product change always asks.
    9. The last line to the owner: start the next run in a new session (`R/` holds the run's state).
!`python3 -I "${CLAUDE_PLUGIN_ROOT}/rules/feedback.py" 11 kiss-harness`

(Agents other than Claude Code: at the end of the run, run `python3 -I <the KISS plugin folder>/rules/feedback.py 11 kiss-harness` and follow what it prints.)

**The clock:** the budget is 10 minutes per ticket plus 2 hours for the reviews and fix rounds, plus the facts
file's `Full check time:`. Put "Time: elapsed
Ns of a Ms budget." in each message to a subagent (`prompt.py` does it with `ELAPSED`). Past the budget, a gate comes
before the next round.

## Side tasks

Work outside the tickets goes to kiss-mini: [references/side-tasks.md](references/side-tasks.md).

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
- Read a subagent's report as a claim: check its JSON against `git`, `tickets.py check` and the files.
- The owner's word decides every decision and every gate; a standing yes in the facts file is the owner's word.

## Traps

Read [references/traps.md](references/traps.md) once, before step 3; the implementer and reviewer read it too.
