# What Changed Reference

Use this when the user asks what changed, what a long coding run did, or what is different in the repo.

## Read-Only Commands

Prefer these commands:

```bash
git status --short
git diff --stat
git diff --name-only
git diff
```

Do not run `git add`, `git commit`, `git checkout`, `git reset`, `git clean`, package installs, formatters, or code generators.

## Analysis

Group changes by user-visible purpose:

| Area | What changed | Improvement | Risk |
| --- | --- | --- | --- |

Look for:

- feature behavior
- setup or config changes
- tests added or removed
- public API changes
- risky areas such as auth, data deletion, payments, migrations, permissions, and secrets

## Output

Start with the change table. Add a graph if files now depend on each other differently.

End with:

```text
Next step
1. Run the most relevant verification command, or ask me to inspect a specific area.
```
