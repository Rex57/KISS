---
name: kiss-system-design
description: Turn a new product idea into a product brief, a decision map, a system design document and an ordered run plan of kiss-harness runs. First version. Use for a product too big for one harness run; continue a design with its name.
disable-model-invocation: true
allowed-tools: Bash(python3 -I "${CLAUDE_PLUGIN_ROOT}/rules/feedback.py" *)
---

# KISS system design (first version)

You find the way from a product idea to a plan of harness runs: you plan, you do not build. Each decision is the
owner's; facts are yours to look up. `SD` is this skill's folder (the folder of this file). The rules and the file
formats are in [references/map.md](references/map.md): read it once, before step 2.

**A design** has a short name (`<name>`, lower case with hyphens). Its working files live in
`<repo>/.kiss/design/<name>/`: `brief.md`, `map.md` and one file per decision in `decisions/`. That folder stays out
of git: when `git -C "<repo>" check-ignore -q .kiss/design/x` fails, add the line `.kiss/design/` to the file that
`git -C "<repo>" rev-parse --git-path info/exclude` names, and say so. **Continue a design** in a new session with
`/kiss:kiss-system-design <name>` (or its name in your words): read `map.md`, then go on at step 4, or at step 5
when no decision is open.

1. **Size check.** Ask what the owner wants to build, and what "done" looks like. When it fits one harness run (one
   feature, one spec and its tickets, no open decision that needs research, a prototype or another session), stop:
   tell the owner to start kiss-harness with the idea as its request, and write no design file. Done when the
   owner agrees that it needs a design, or kiss-harness is named.
2. **Destination: the product brief.** Call the Skill tool with `mattpocock-skills:grilling` and
   `mattpocock-skills:domain-modeling` (Claude Code and Codex names; without them, ask in rounds of `D<n>` with your
   recommended answer, and keep a glossary in the brief). Settle the destination: the product, who uses it, the
   problem, what done looks like, the hard limits. Write `brief.md`. Done when the owner says the brief is right.
3. **The decision map.** Ask breadth-first across the whole product: every open decision you can state exactly now.
   Write `map.md` with its parts: Destination, Notes, Decisions so far, Open decisions (each typed `research`,
   `prototype`, `grilling` or `task`, with what blocks it), Not yet clear, Out of scope. Write one file per open
   decision in `decisions/`. A question you cannot state exactly yet goes to Not yet clear; work beyond the
   destination goes to Out of scope. Then start each `research` decision in the background (step 4). Done when
   every open decision has its file and its type.
4. **Work the map, one decision at a time** (research may run side by side). Take the first open decision that
   nothing open blocks, unless the owner names one. Settle it by its type:
   - `research`: in the background, through kiss-mini (`/kiss-mini ask <question>` or its hand-off) when it is
     installed, else a subagent that calls the Skill tool with `mattpocock-skills:research`. Its findings go into
     the decision file; the owner confirms what they decide.
   - `prototype`: call `mattpocock-skills:prototype` for a cheap, throwaway thing the owner can try (a state
     model, a UI), in the scratch folder or on a branch that is never merged; the owner decides from it.
   - `grilling`: `mattpocock-skills:grilling` and `mattpocock-skills:domain-modeling` with the owner. Only the owner
     answers; never answer your own question.
   - `task`: the work that must happen before a decision (an account, access, a data sample). Do it when you can,
     else give the owner a checklist.
   Write the answer and the rejected options with their reasons into the decision file, close it, and add one line
   to Decisions so far. Then add each new decision the answer made exact, and move each part of Not yet clear that
   is now exact into a decision file. A decision that turns out to lie beyond the destination goes to Out of scope.
   Done when no decision is open and Not yet clear is empty or the owner moves its rest to Out of scope.
5. **The system design document.** When no decision is open, write it into the project's docs (where a new page
   goes by the docs map, else `docs/design/<name>.md`) with these sections: Context, Goals and non-goals, Modules
   and interfaces (in `mattpocock-skills:codebase-design`'s words: module, interface, seam, depth; call that skill
   first), Data, Rejected options (each with its reason, and its decision named by title), Security, Privacy, Observability. When
   the project has a docs gate (`Docs gate:` in `.kiss/project.md`), give the page its status line and link it from
   the docs map, so kiss-housekeeping keeps it true. Name each decision by its title and copy its reason into the page; never link into `.kiss/design/`
   (it is git-ignored: a clone and a docs gate cannot see it). Done when every section is filled and the owner says yes.
6. **The run plan.** Beside it, `docs/design/<name>-run-plan.md` (or its docs-map place): an ordered list of run
   briefs. Each brief is one harness run: its name, its deliverable (what the owner can see working), the decisions
   it builds on (by name, with the design document's section), the briefs it depends on, and the request to give
   kiss-harness, with no link into `.kiss/design/`. Harness step 1 starts from the brief and asks only what is still open. Done when every goal of the
   design document is in a brief and the owner says yes.
7. **The loop back.** When a harness run finds that a design decision is wrong, open it again in `map.md` (Open
   decisions, with what the run found), settle it by step 4, update the design document and the run briefs it
   changes, and tell the owner which runs change. Done when the map has no open decision again.
!`python3 -I "${CLAUDE_PLUGIN_ROOT}/rules/feedback.py" 8 kiss-system-design`

(Agents other than Claude Code: at the end of the run, run `python3 -I <the KISS plugin folder>/rules/feedback.py 8 kiss-system-design` and follow what it prints.)
