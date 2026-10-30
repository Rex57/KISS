# The questions, the spec and the tickets

The controller's rules for steps 1 and 2. The interview, spec and ticket rules are adapted from Matt Pocock's skills
`grilling`, `to-spec` and `to-tickets` (https://github.com/mattpocock/skills; MIT License, Copyright (c) 2026 Matt
Pocock), so that a run without his skills follows the same rules.

## The questions (step 1)

When the `grilling` skill is installed, use it. Otherwise, ask the same way:

- **Map the decisions as a tree:** each decision opens the ones that depend on it.
- **Ask in rounds.** One round asks every open decision whose earlier decisions are settled (the frontier). Number
  each question and give your recommended answer, worded so that "yes" accepts it. Then wait for the answers.
- **Facts are your job, decisions are the owner's.** Never ask the owner what the code, the docs or a tool can tell
  you: look it up (a subagent, for a long search). Put each decision to the owner.
- **Stop when no decision is open**, then ask the owner to confirm that you share one understanding. Act only after
  that yes.

Write each settled decision into `R/decisions.md` at once, one line each:
`D<n>. <the question>: <the answer> (owner | recommended, accepted)`.
When the facts file sets domain docs on, also use the `domain-modeling` skill (or the project's own way) for a term
that needs a fixed meaning (`GLOSSARY.md`) and for a decision that is hard to reverse (an ADR).

## The spec (step 1)

Write `R/spec.md` from `templates/spec.md`. Read the code first, and use the project's glossary words.

- **Problem and solution** from the user's point of view, not the code's.
- **User stories:** a long numbered list, `As a <actor>, I want <feature>, so that <benefit>`, that covers every
  part of the feature.
- **Implementation decisions:** the modules to build or change, their interfaces, schema changes, API contracts and
  the owner's technical rulings. No file paths and no code: they go stale. A prototype's snippet that states a
  decision better than words (a state machine, a schema, a type) may stay, marked as from a prototype.
- **Testing decisions:** a good test checks behaviour through a public interface, never internals. The **seams** are
  the public interfaces the tests go through: prefer an existing seam, the highest one, and as few as possible (one is
  best). Name similar tests in the repo to copy. **Confirm the seams with the owner.**
- **Out of scope**, and **Done means**: the steps by which the owner checks the result in the running product.

## The tickets (step 2)

- **Tracer bullets:** each ticket is a thin slice through every layer it needs (schema, API, UI, tests), never one
  layer alone. A finished ticket can be shown or checked on its own.
- **Size:** each ticket fits one fresh context window.
- **Refactor first:** "make the change easy, then make the easy change". A refactor that makes later tickets easy is
  its own ticket, first.
- **Blocking links:** `depends_on` lists the tickets that must be done first. A ticket with none can start first.
  The implementer works in file order, so put each ticket after the tickets it depends on.
- **A wide refactor** (one mechanical change that breaks many callers at once, such as a renamed column) is not a
  tracer bullet. Do it in three stages: add the new form beside the old one; move the callers in batches sized by
  how far the change reaches, each batch a ticket after the first stage; then remove the old form, in a ticket after
  every batch. When a batch cannot pass alone, end with one ticket that joins and checks them all.
- **Acceptance lines** are the definition of done. Each one names its seam: `through <seam>: <what a person or a
  test sees>`. No file paths or code in a ticket's `spec` or `acceptance`; `files` and `symbols` are only hints for
  the CodeGraph seed.
- **Ask the owner** about the breakdown: is the size right (too large, too small), is each blocking link real,
  should a ticket be merged or split? Change the list until the owner says yes. That yes also confirms the seams.
