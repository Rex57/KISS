# The look back at the close (step 10)

Adapted from Matt Pocock's `retro` skill (https://github.com/mattpocock/skills; MIT License, Copyright (c) 2026 Matt
Pocock). It improves the project's environment for the next run, never the product code of this run. Its full license: THIRD_PARTY_NOTICES.md at the KISS repo root.

Read the run's own record: `R/progress.md`, `R/decisions.md`, the findings and fix rounds, the side tasks, and the
messages you sent. Look for these candidates:

- **A mechanical mistake** (a fixed pattern, a banned call, an import shape, a file in the wrong place, a step
  forgotten twice) that an automated check could catch: propose a check (a test, a script, a lint rule, a hook) in
  the project's own guardrail, the cheapest one its language and its pre-commit hook or CI allow. Read the project's
  check command first: a check that exists but is not wired, or is broken, is the finding. A project with no
  guardrail at all is a finding too. Prefer a check to a rule.
- **A judgement call** that no check can make (cross-file consistency, "matches the code around it"): propose a rule
  for the facts file's "Rules a reviewer checks". The reviewer enforces rules, not the implementer.
- **Navigation, information, tool cost:** a fact an agent searched long for gets a pointer in the facts file; a
  fact it could not reach gets a way to reach it; an expensive call gets a cheaper one.
- **A steering line that changes nothing:** propose to delete it.
- **A lesson about KISS** itself goes to the KISS owner as file, line and new text (in the feedback block when the
  feedback mode is on), never into the project.

List the candidates for the owner, most severe first, each with its evidence (the progress line or finding). This
joins kiss-housekeeping's fold-back and replaces nothing there. On the owner's yes, write a facts-file rule
yourself; a proposed check becomes a `/kiss-mini` task or a ticket of the next run, never product code of yours.
