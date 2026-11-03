---
name: kiss-doctor
description: Check this device's KISS setup - the CodeGraph rule in the global instructions file, the skills KISS calls and the tools.
disable-model-invocation: true
allowed-tools: Bash(printenv KISS_FEEDBACK)
---

# KISS doctor

You check the setup and report it; the owner installs. `KD` is this skill's folder (the folder of this file).

1. **Run the checks:** `python3 -I "$KD/scripts/doctor.py"`. It checks each agent whose CLI is on PATH; name
   agents to check fewer (`claude`, `codex`, `gemini`, `antigravity`). Per agent: the CodeGraph rule in the global
   instructions file (KISS's `rules/codegraph.md`, found by its bold lead-ins, `@` imports followed), each skill in
   the harness's skill table and KISS's own (installed, enabled, once, callable by the model), and the tools.
   Done when it prints its summary line.
2. **Compare with your own skill list.** The script reads the disk; your skill list is what this session loaded.
   A skill on disk but not in your list needs a reload: `/reload-plugins` in Claude Code, a new session elsewhere.
   The script cannot see Antigravity's plugin folders, so there your list decides. A KISS skill in your list that
   the script calls "not installed" (a session loaded from a plugin folder, or a KISS repo newer than the install)
   is INFO with that reason, never FAIL; in Claude Code the script prints it as INFO itself.
3. **Report** every INFO line with its reason, and every WARN and FAIL line with its fix, taken from the README section in its `[fix: ...]`
   (`$KD/../../README.md`). End the report (before step 5) with one line: "Ready for a KISS run" when no line is FAIL, else the FAIL lines to
   fix first. Done when each WARN and FAIL line has its fix.
4. **Fix on the owner's yes.** The owner installs tools and skills, by the README commands. With a yes you may make
   a file fix: append `$KD/../../rules/codegraph.md` to the global instructions file once (read the file
   first), or delete a `CODEGRAPH_START` block. Then run step 1 again.
5. **KISS feedback**, in every run, also one that stops early or fails: after your last work call, run `printenv KISS_FEEDBACK` as its own tool call, with nothing before or after it in that call. When it prints `1`, read [`rules/feedback.md`](../../rules/feedback.md) and `version` in `gemini-extension.json` at the plugin root, then end your final message with the block (no path outside the KISS repo, none that starts with `/`, `~` or a drive letter). When it prints anything else, or the call is refused or fails, end your final message with your report alone, with no line about this step.
