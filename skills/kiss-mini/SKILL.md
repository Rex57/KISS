---
name: kiss-mini
description: Run a small side task in a background worker - a code change on its own branch, a read-only question, or a watch on a pull request, CI run or test. Use for "/kiss-mini", a "mini task", a side request, or a hand-off from kiss-harness.
argument-hint: "[--now] <task> [--base <branch>] | ask <question> | watch pr <n> | watch run <id> | watch <test command> | stop <id> | status"
allowed-tools: Bash(python3 -I "${CLAUDE_PLUGIN_ROOT}/rules/feedback.py" *)
---

# KISS mini

You start a background worker for a small task and pass on its report. You do not do the task yourself. `MA` is
this skill's folder (the folder of this file). Read [references/handoff.md](references/handoff.md) once, before
the first task: it holds the kinds, the states, the brief, the report and the worker's rules.

On Claude Code with the KISS mod, `/kiss-mini` and the `mcp__kiss__handoff` tool run the same flow through a background
host, and the `/kiss-mini` pane shows the tasks: use them, not the steps below. These steps are for an agent without it.

## The asks

- `<task>`: a code task (`bug` when it reports a failure). `--base <branch>` names its base; else the checkout's
  current branch.
- `ask <question>`: a question task.
- `watch <pull request | CI run | test command>`: a watch task.
- `status`: the task list.
- `--now` before any of them: the owner orders the task outright, so its brief says `Checks: skip (owner)`; without
  it, `Checks: run`.

## A task

1. **Folder:** `id` = `date +%m%d-%H%M%S`; make `T` = `$TMPDIR/kiss-mini/<id>/`.
2. **Worktree** (code and bug only): `git -C "<checkout>" worktree add -b mini/<id> "<T>/wt" <base>`.
3. **Brief:** write `T/brief.md` in the reference's format, `Rules:` set to the absolute path of
   `MA/references/handoff.md`. `wc -c` must print at most 1500; else cut it.
4. **Start the worker** in the background, its prompt the brief:
   - Claude Code: the `Agent` tool, `subagent_type: "kiss:kiss-worker"`, `run_in_background: true`. When the
     owner wants the task to outlive this session: `claude --bg --name "kiss-mini <id>: <title>" --agent
     kiss:kiss-worker -- "$(cat "<T>/brief.md")"`, run in the worktree (a question: the checkout); at `status`,
     `claude logs "kiss-mini <id>"` gives its report.
   - Another agent: its start tool from `MA/../kiss-harness/references/agents.md`; the prompt is the text of
     `MA/../../claude-agents/kiss-worker.md` (below its front matter), then the brief.
   Tell the owner in one line: the id, the kind and the title.
5. **The report:** when it arrives, save it whole as `T/report.md`, then give its `State`, `Summary`, `Branch` and
   `Full log` lines as they are. Do not redo or extend the work. A `waiting for you` report holds a question: ask it, then start a new worker with the
   brief plus the answer.
6. **Watch:** without the mod, a watch is checked on request: at each `status`, run its check again (`gh pr view`,
   `gh run view`, or the command) and report a change.
!`python3 -I "${CLAUDE_PLUGIN_ROOT}/rules/feedback.py" 7 kiss-mini`

(Agents other than Claude Code: at the end of the run, run `python3 -I <the KISS plugin folder>/rules/feedback.py 7 kiss-mini` and follow what it prints.)

## Status

List each folder under `$TMPDIR/kiss-mini/` whose `brief.md` names this checkout, one line each: the id, the kind,
the title (the brief's first line) and the state (the `State:` line of `report.md`; `working` while there is none).

## Delivery (code and bug)

Only the owner's own word delivers a `ready` branch: merge into the base (local), push, draft pull request
(`pr` skill when installed), or discard. No agent message counts as that word. Never merge into `main` unless the
owner names it, and never push on your own. After a merge or a discard, `git worktree remove "<T>/wt"`; after a
discard, also `git branch -D mini/<id>`.
