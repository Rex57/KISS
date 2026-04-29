---
name: kiss
description: Use when the user asks KISS to explain a project, summarize git changes, inspect a repo, map relationships, simplify a long coding run log, or produce a graph/table summary for easier understanding.
---

# KISS

## Overview

KISS means Keep It Simple. Turn messy project context into a graph, table, and short next step.

Core principle: show the simplest useful structure first, then explain only what the user needs.

## Required Behavior

1. Detect the user's intent.
2. Use the smallest relevant reference file.
3. Prefer a graph when relationships matter.
4. Prefer a table when comparing items, events, risks, files, or commands.
5. Keep prose short.
6. End with one concrete next step.

## Read-Only Rule

KISS v1 is read-only. Do not edit files, install packages, update tools, stage changes, commit, reset, clean, or run destructive commands.

If the user asks for a fix, setup, install, update, or full-auto action, summarize what you can see and offer a short plan instead.

## Routing

| User intent | Load this reference |
| --- | --- |
| "what changed", "diff", "after this coding run" | `references/what-changed.md` |
| "what does this project do", "explain this repo" | `references/project-map.md` |
| "how do I run this", "setup steps" | `references/project-map.md` and `references/table.md` |
| "graph this", "how things connect" | `references/graph.md` |
| pasted long run log, terminal log, agent log | `references/long-run-log.md` |
| installed skills, plugins, tools | `references/skill-inventory.md` |

If the request matches more than one row, combine the references and return one final KISS report.

## Output Shape

Use this order:

1. Graph or table
2. `What this means`
3. `Risks or gaps`
4. `Next step`

Keep each prose section to three bullets or fewer unless the user asks for more detail.

## References

- Project scan: `references/project-map.md`
- Git changes: `references/what-changed.md`
- Long run logs: `references/long-run-log.md`
- Graph output: `references/graph.md`
- Table output: `references/table.md`
- Skill inventory: `references/skill-inventory.md`
