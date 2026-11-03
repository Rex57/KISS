# Architecture candidates (step 5)

Adapted from Matt Pocock's `improve-codebase-architecture` skill (https://github.com/mattpocock/skills; MIT License,
Copyright (c) 2026 Matt Pocock). KISS keeps its rules and gives a ranked list instead of its HTML report.

- **Scope first.** A deepening pays off by making future changes easier, so look first where the code changes:
  the hot spots from the git history (step 2). With no clear hot spot, widen the net. An area the owner names
  comes first.
- **Read the domain words** first: the project's glossary and its decision records (ADRs) in the area. A candidate
  that goes against a decision record is listed only when the friction is real enough to reopen it, and says so.
- **Look for friction:** one concept that needs many small modules to understand; a **shallow** module, whose
  interface is nearly as complex as its implementation; a pure function pulled out only to test it, while the bugs
  hide in how it is called (no **locality**); modules that leak across their **seam**; code that is untested or
  hard to test through its interface.
- **The deletion test:** for a module you suspect is shallow, ask whether deleting it would concentrate the
  complexity in one place or only move it. "Concentrates" is the signal.
- **Words:** module, interface, depth, seam, adapter, leverage, locality (`codebase-design`), never "component",
  "service", "API" or "boundary". One adapter is a guessed seam; two make it real.
- **Each candidate:** the files, the problem, the change in plain words, the gain in locality and leverage and in
  the tests, and a strength: `Strong`, `Worth exploring` or `Speculative`. Do not design the new interface here:
  that is the harness run's step 1.
