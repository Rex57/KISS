# The map and its decisions

Adapted from Matt Pocock's `wayfinder` skill (https://github.com/mattpocock/skills; MIT License, Copyright (c) 2026
Matt Pocock). KISS keeps its rules and keeps the map in files instead of an issue tracker. Its full license: THIRD_PARTY_NOTICES.md at the KISS repo root.

## Rules

- **Plan, do not build.** Each decision file settles a decision; the design is done when nothing is left to decide
  before the first harness run. The pull to build is the sign that you reached the edge of the map.
- **Name the destination first:** it fixes the scope, and every session reads it before it picks a decision.
- **The map is an index:** each decision lives in one place, its file; the map gives a one-line gist and a link.
  Refer to a decision by its title, never by a bare number.
- **Types.** `research` (the agent alone: a fact outside the repo that a decision waits on), `prototype` (with the
  owner: a cheap rough thing to react to, when "how should it look or behave" is the question), `grilling` (with the
  owner: talk, the default), `task` (work that must happen before a decision; the agent does it, or gives the owner
  a checklist). In a decision with the owner, only the owner answers.
- **Not yet clear (fog).** The test is whether you can state the question exactly now, not whether you can answer
  it. Exact, even if blocked: a decision file. Not exact yet: a line in Not yet clear, coarser than a decision; one
  line may become several decisions, or none. It holds nothing decided, nothing open, nothing out of scope.
- **Out of scope.** Work beyond the destination. It never comes back into this design; a new destination is a new
  design. A decision found to lie beyond it is closed with one line there and the reason, not in Decisions so far.
- **One decision per session**, except research, which may run side by side.

## `map.md`

```markdown
# <design name>: map

## Destination
<what the end of this map looks like, in one or two lines>

## Notes
<the domain, the skills each session uses, the owner's standing preferences>

## Decisions so far
- [<decision title>](decisions/<nn>-<slug>.md): <one-line gist of the answer>

## Open decisions
- [<decision title>](decisions/<nn>-<slug>.md): <type>; blocked by <titles, or "nothing">

## Not yet clear
- <a question you cannot state exactly yet>

## Out of scope
- <the work, and why it is beyond the destination>
```

## `decisions/<nn>-<slug>.md`

```markdown
# <decision title>

Type: research | prototype | grilling | task. Status: open | settled (<date>). Blocked by: <titles, or nothing>.

## Question
<the decision this file settles>

## Answer
<the decision, and the facts or the prototype it rests on>

## Rejected options
- <option>: <why not>
```

## `brief.md`

Product, users, problem, what done looks like, hard limits, and the glossary (one line per term).
