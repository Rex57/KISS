## KISS feedback — the rule

Every KISS skill ends its run with this check. It is off by default.

1. **Read the switch:** `printenv KISS_FEEDBACK`. When it does not print `1`, stop here: add nothing, and do not
   name this rule or the mode.
2. **When it prints `1`,** end your final message with one block, the last thing in the message, in this form:

   ```
   ## KISS feedback

   Skill: <the skill's name>, KISS <version>
   What went wrong or was unclear:
   - <one line each; "nothing" when the run went as the skill says>
   Proposed changes:
   - <file in the KISS repo, e.g. skills/kiss-doctor/SKILL.md>, line <n>: <the new text>
   ```

   The version is `version` in `gemini-extension.json` at the plugin root (all four manifests carry the same one).
   Each proposed change names a KISS file, the line, and the new text, so the KISS owner can paste the block into a
   session in the KISS repo and apply it. No change to propose: write "none".
3. **Keep the project out.** A user can post the block as a public issue on the KISS repo. It never holds a
   project's name, a path of the machine or the project (only paths inside the KISS repo), code, data, a URL of the
   project, or a secret. Describe the problem in general words ("a repo with two test folders"), not with the
   project's own.

A lesson about the project goes into the project's facts file, never into this block.
