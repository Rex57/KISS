# Hand-off: the brief, the report and the worker's rules

The kiss-mini-agent skill, its mod, the `kiss-worker` agent and kiss-harness all read this file. `T` is a task's
folder, `$TMPDIR/kiss-mini/<id>/` (`/tmp` when `TMPDIR` is unset), never in the checkout. It holds `brief.md` and,
at the end, `report.md` (the full log), which the receiver of the report writes (a subagent may not write it).

## Kinds and states

- **Kinds:** `code` (a small change, on its own branch), `bug` (a code task that starts from a failure),
  `question` (read-only: an answer, no change), `watch` (a pull request, a CI run or a test command).
- **States:** working, waiting for you, ready, watching, done, failed. A code or bug task that has a branch to
  deliver ends `ready`; a question ends `done`; a worker that needs a person stops `waiting for you`.

## The brief (at most 1,500 characters)

```markdown
# Mini task <id>: <title>
Kind: code | bug | question | watch
Checkout: <absolute path>    Base: <branch>    Branch: mini/<id>    Worktree: <absolute path>
Task folder: <T>             Return: harness | owner    Owner order: yes | no
Rules: <the absolute path of this file>
Summary: <one line: what must happen>
Current behaviour: <what happens now>
Expected behaviour: <what happens after the work>
Key interfaces: <files by path, functions, commands; never copies of their text>
Acceptance checks:
- <a command or a check that shows done>
Out of scope: <what the worker leaves alone>
Suggested skills: <the skills for this kind, from the table below>
```

A question task leaves out `Base`, `Branch` and `Worktree`. Point to specs, issues, commits and logs by path or
URL; do not copy them in. No secrets: no keys, passwords or personal data. Count the characters before the send.

## The report

The worker's final message. The receiver saves the whole message as `T/report.md` and passes on only these lines:

```markdown
State: ready | done | failed | waiting for you
Summary: <at most 600 characters: what changed or the answer, or the question to the owner>
Branch: mini/<id>    Commits: <sha> <subject>, ...
Tests: <each acceptance check and its result>
Full log: <T>/report.md
```

A question task writes `Branch: none`. Below these lines comes the full text: the whole answer, the commands run
and their output. A code or bug task's full text ends with a `## Pull request body` section, written with the `pr`
skill when it is installed: a draft pull request takes it as its body.

## The worker's rules

1. **Three checks before work**, unless the brief says `Owner order: yes`: verify the claim (for a bug, run a
   command that shows the failure); search for code that already does it (CodeGraph when the repo has an index,
   else a word search), and say where you looked; compare with `Out of scope`. When a check fails, stop and report
   it.
2. **Skills for the kind**, each when it is installed:

   | Kind | Skills |
   |---|---|
   | bug | `diagnosing-bugs`, then `tdd` |
   | code | `tdd`, `ponytail`, CodeGraph |
   | question | `research` |
   | a pull request body | `pr` |

3. **Where to work:** a code or bug task works only in its worktree, on its branch, and ends with one commit
   that adds the files the task changed by explicit path, never build or test output (`__pycache__`, `.pyc`,
   `dist/`); it never pushes, merges or opens a pull request. A question task changes no file in the checkout.
4. **Conduct:** speak only when a person must act or can use a result. Confirm a step once, not again. Ask one
   concrete question at a time. Stop at a design choice and ask it. Mark a draft as unfinished.
5. **End** with the report as your final message; write no report file.

## Credit

The brief format, the three checks and the suggested-skills line copy rules from Matt Pocock's skills `handoff`,
`claude-handoff` and `triage` (https://github.com/mattpocock/skills), MIT License, Copyright (c) 2026 Matt Pocock.
