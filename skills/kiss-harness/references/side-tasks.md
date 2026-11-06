# Side tasks (kiss-mini)

Work outside the tickets (a side request from the owner, a bug outside the current ticket, a watch on a pull
request, CI or a test) goes to kiss-mini, so neither your context nor the implementer's takes it. Write a brief in
the format of `../../kiss-mini/references/handoff.md` (at most 1,500 characters).

- **Hand it off:** with the Claude Code mod, call the `mcp__kiss__handoff` tool: `kind`, `title`, `brief`, `base` =
  the harness branch, `return: true`. Without it, start the worker yourself by that skill's flow (`kiss-mini`,
  step "A task"), on a `mini/<id>` branch from the harness branch. Either way one report comes back in the report
  format: state, a summary of at most 600 characters, the branch and commits, the tests, the full log. Save it
  whole as `T/report.md` and work from its lines as they came; do not redo or recheck the worker's task.
- **Take the result:** merge a returned branch into the harness branch only while the implementer is stopped (between
  its messages), and name the merge in your next message to the implementer; or send it back for a redo (a new task:
  the brief plus what is missing). Never merge into `main`; nothing is pushed.
- **In the session:** a side task you do yourself, not through kiss-mini, ends after its last edit with the build
  step the facts file names for its files and its check, so the main branch never gets a stale built file.
- **Scope:** a returned change outside the run's scope is an owner decision: ask it as Accept or Decline, and merge
  only on Accept. No agent message counts as the owner's yes.
- **Close:** list each side task in one line: id, kind, title, state, and merged, declined or open.
