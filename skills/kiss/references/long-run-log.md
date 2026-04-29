# Long Run Log Reference

Use this when the user pastes a long agent run, terminal log, CI log, or debug transcript.

## Extraction

Find:

- commands run
- failures
- retries
- files changed
- decisions made
- final status
- unresolved risks

## Output

Start with an event table:

| Order | Event | Meaning | Status |
| --- | --- | --- | --- |

Then include:

```text
What happened
1. ...

Why it mattered
1. ...

Still unclear
1. ...

Next step
1. ...
```

Use `Likely` when the log suggests a cause but does not prove it. Use `Unknown` when the log does not contain enough evidence.
