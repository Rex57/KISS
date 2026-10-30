# Traps

The traps that cost a run time in any project. The controller, the implementer and the reviewer read this file once.
A project's own traps are in its facts file (`.kiss/project.md`).

- Use absolute paths in every command: a shell that resets its folder has built in the main checkout before.
- zsh: write heredocs as `<<'EOF'` (an unquoted one runs every backtick); zsh does not split an unquoted `$VAR`
  into words; macOS has no `timeout`.
- A test that reads the clock twice flakes at a second boundary: read it once per stamp.
- A ticket with a time window (freshness, a timeout, staleness) needs a test that runs the clock past that window:
  a test inside the window passes while the feature fails later.
- A worktree has no CodeGraph watcher: `codegraph sync -q "W"` after each commit.
- A seed or a sync can run for minutes: give it a 10-minute timeout (Claude Code: the Bash tool's
  `timeout: 600000`), or a short default timeout kills it and the agent runs it again.
- A tool result that shows a preview and names a file: read the file before you act.
