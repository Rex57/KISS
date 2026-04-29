# Skill Inventory Reference

Use this when KISS needs to know which local skills, plugins, or helper workflows exist.

## Read-Only Locations

Check relevant paths if they exist:

```text
~/.codex/skills
~/.codex/plugins
~/.agents/skills
~/.agents/plugins
.codex
.agents
```

Use read-only commands such as `find`, `rg --files`, `ls`, and `sed`.

## Output

| Tool | Found | Type | How KISS can use it |
| --- | --- | --- | --- |

## Rules

- Do not install missing tools in v1.
- Do not update tools in v1.
- Mention missing tools only as suggestions.
- If Superpowers is installed, mention it can help with debugging, planning, verification, and branch completion.
- If Browser Use is installed, mention it can help future website inspection.
- If Impeccable is installed, mention it can help product and design workflow understanding.
