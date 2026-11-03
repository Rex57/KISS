---
name: kiss-check-update
description: The KISS owner's check of every upstream source KISS calls or copies (Matt Pocock's skills, ponytail, CodeGraph, the Claude Code mods API) against what is out now, then the port, the tests and the record update. Only in the KISS repo; not part of the plugin.
disable-model-invocation: true
allowed-tools: Bash(python3 -I "${CLAUDE_SKILL_DIR}/../../../rules/feedback.py" *)
---

# KISS check update

You keep KISS in step with its upstream sources; the owner decides what to port and when to release. `CU` is this
skill's folder (the folder of this file); the record is `$CU/upstream.json` (upstream repos, tags, paths and
fingerprints only, never a path of this device). Run every command from the KISS repo root, with the network
(`gh`, `npm`).

1. **Run the check:** `python3 -I "$CU/scripts/check_update.py"`. One line per source: `same`, or one line per
   finding: a new release with its compare link, a copied file `changed` (with the KISS files that copy it and the
   compare link) or `gone`, a called skill `no longer callable` (now user-only) or gone, a CodeGraph `flag gone`, a
   new Claude Code build with the result of `claude plugin validate` and `claude plugin test`. Exit 1 on any change.
   Done when every source has its line. All `same`: stop here and say so.
2. **Read each diff.** Open each compare link (`gh api repos/<repo>/compare/<old>...<new>`) and read what changed
   in the files the record names. For each finding, write one line: what changed, which KISS file it touches, and
   whether to port it. Done when each finding has its line.
3. **Port what fits**, on a branch, in the KISS files the record names: a copied rule that changed, a skill path that
   moved, a flag that was renamed. A large change (a new flow, many files) becomes a harness run instead
   (`kiss-harness`, the finding as its request). A called skill that turned user-only leaves KISS's skill table, or
   KISS keeps its own copy of the rule. Done when each finding is ported, handed to a harness run, or set aside by
   the owner.
4. **Run the tests:** every `--selftest` under `skills/` and this skill's own, `claude plugin validate .`,
   `claude plugin test .`, and the leak scan of `.kiss/project.md`. Done when all pass.
5. **Update the record** for the sources you ported, only those:
   `python3 -I "$CU/scripts/check_update.py" --update <source name>...`, then run step 1 again: those sources say
   `same`. Commit the port and the record by explicit path. Done when step 1 shows `same` for them.
6. **Release on the owner's go:** the version in the four manifests, a tag `v<version>`, a push and a GitHub
   release only when the owner says so. Done when the owner has the release or has said not now.
!`python3 -I "${CLAUDE_SKILL_DIR}/../../../rules/feedback.py" 7 kiss-check-update`

(Agents other than Claude Code: at the end of the run, run `python3 -I <the KISS repo>/rules/feedback.py 7 kiss-check-update` and follow what it prints.)
