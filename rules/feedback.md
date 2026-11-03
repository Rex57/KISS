## KISS feedback — the rule

The feedback mode is off by default. When `KISS_FEEDBACK` is `1`, `rules/feedback.py` prints this rule, with the
skill's name and the KISS version filled in, as the skill's last step; with any other value the step does not exist.

1. **End your final message with one block**, the last thing in the message, in this form:

   ```
   ## KISS feedback

   Skill: <the skill's name>, KISS <version>
   What went wrong or was unclear:
   - <one line each; "nothing" when the run went as the skill says>
   Proposed changes:
   - <file in the KISS repo, e.g. skills/kiss-doctor/SKILL.md>, line <n>: <the new text>
   ```

   Each proposed change names a KISS file, the line, and the new text, so the KISS owner can paste the block into a
   session in the KISS repo and apply it. No change to propose: write "none".
2. **Keep the project out.** A user can post the block as a public issue on the KISS repo. It never holds a
   project's name, a path of the machine or the project (only paths inside the KISS repo; never one that starts with
   `/`, `~` or a drive letter), code, data, a URL of the project, or a secret. Describe the problem in general words
   ("a repo with two test folders"), not with the project's own.
3. **One block per run.** A KISS skill that runs inside another KISS skill's run (kiss-housekeeping's Upkeep in a
   harness close) gives no block of its own. The outer skill's one block covers the whole run and names both
   skills, also when you followed the inner skill's steps without loading it:
   `Skill: <outer skill> (with <inner skill>), KISS <version>`.

A lesson about the project goes into the project's facts file, never into this block.
