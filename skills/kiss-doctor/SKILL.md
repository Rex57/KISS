---
name: kiss-doctor
description: Check this device's KISS setup - the CodeGraph rule in the global instructions file, the skills KISS calls and the tools - and, with `setup`, show a plan to install what is missing.
disable-model-invocation: true
allowed-tools: Bash(python3 -I "${CLAUDE_PLUGIN_ROOT}/rules/feedback.py" *)
---

# KISS doctor

You check the setup and report it. KISS installs only on the owner's request, from the official sources, after the
owner sees each command. `KD` is this skill's folder (the folder of this file).

**Feedback on or off.** When the owner asks `kiss-doctor feedback on` (or `feedback off`), run only
`python3 -I "$KD/scripts/doctor.py" feedback on` (or `off`), report the lines it prints (the file it changed, its
backup, that a new session is needed, the export line for the other agents), and stop. It sets only
`env.KISS_FEEDBACK` in Claude Code's user settings (`"1"` or `"0"`) and edits no shell profile.

**Setup.** When the owner asks `kiss-doctor setup`, run only `python3 -I "$KD/scripts/doctor.py" setup`, followed
by the agents the owner names (`setup claude`), if any: then the plan and the checks cover only those. It finds
the OS, the shell, the package manager and the agents on PATH, runs the checks, and prints a numbered plan of what
is missing: each item with its command, its source and what it changes, then the steps only the owner can do (a
`sudo` command, Antigravity's copy steps, Codex's `/hooks` trust, a new session) and the optional links. Show the
plan as printed, ask "all, none, or the numbers?", and wait. The owner's answer is the go: run only the call the
plan's last line names, `python3 -I "$KD/scripts/doctor.py" setup [<agents>] --apply <answer> --plan <id>`, with
`all`, `none` or the owner's numbers (`1,3`) as the answer and the plan id the plan printed; a plan that changed
since the owner saw it is refused, so show it again. An owner who skips an agent's items for now: run setup again
with only the other agents, so its checks leave out the skipped agent. Each command stops after 5 minutes as a FAIL, so the call needs up to 5 minutes per command it runs:
for one or two items give it a 10-minute timeout (Claude Code: the Bash tool's `timeout: 600000`); for more, run it
in the background (Claude Code: `run_in_background`) and wait for it to end.
Never type an install command yourself; every command comes from the script's install table. The
script runs the items one at a time, stops at the first failure, runs the checks again, and prints the steps by
hand. Report what it printed: each item done, a FAIL with its output and the items not run, the checks again, and
the manual steps (a `sudo` command, Antigravity's copy steps, Codex's `/hooks` trust, a new session and its login).
An answer the script refuses: show its line and ask again.

1. **Run the checks:** `python3 -I "$KD/scripts/doctor.py"`. It checks each agent whose CLI is on PATH; name
   agents to check fewer (`claude`, `codex`, `gemini`, `antigravity`). Per agent: the CodeGraph rule in the global
   instructions file (KISS's `rules/codegraph.md`, found by its bold lead-ins, `@` imports followed), each skill in
   the harness's skill table and KISS's own (installed, enabled, once, callable by the model), and the tools.
   Done when it prints its summary line.
2. **Compare with your own skill list.** The script reads the disk; your skill list is what this session loaded.
   A skill on disk but not in your list needs a reload: `/reload-plugins` in Claude Code, a new session elsewhere.
   A line marked `user-only: never in the model's list` is a skill only the owner starts: it is never in your
   list, so report no reload for it.
   The script cannot see Antigravity's plugin folders, so there your list decides. A KISS skill in your list that
   the script calls "not installed" (a session loaded from a plugin folder, or a KISS repo newer than the install)
   is INFO with that reason, never FAIL; in Claude Code the script prints it as INFO itself.
3. **Report** the feedback mode line (on or off, and where it is set), every INFO line with its reason, and every WARN and FAIL line with its fix, taken from the README section in its `[fix: ...]`
   (`$KD/../../README.md`). End the report with one line: "Ready for a KISS run" when no line is FAIL, else the FAIL lines to
   fix first. Done when each WARN and FAIL line has its fix.
4. **Fix on the owner's yes.** The owner installs tools, skills and the CodeGraph rule with `kiss-doctor setup`
   (or the README links); never append the rule by hand. With a yes, your one file fix is to delete a
   `CODEGRAPH_START` block (read the file first). Then run step 1 again.
!`python3 -I "${CLAUDE_PLUGIN_ROOT}/rules/feedback.py" 5 kiss-doctor`

(Agents other than Claude Code: at the end of the run, run `python3 -I <the KISS plugin folder>/rules/feedback.py 5 kiss-doctor` and follow what it prints.)
