# Subagents on each agent

The harness needs three acts: **start** a subagent with a filled prompt, **wait** for its final message, and
**continue** the same subagent with a new message (the next ticket, a fix round, a recheck). Use your agent's row.
When your tool list differs from this page, trust the tool list.

| Agent | Start | Continue the same subagent | Notes |
|---|---|---|---|
| Claude Code | `Agent` tool, `subagent_type: "general-purpose"`, the prompt, `model` (the implementer: `opus`, effort `medium`), `run_in_background: true` | `SendMessage` to the agent's id | You are told when it finishes: do not poll |
| Codex | `spawn_agent` with the prompt; set the model and the reasoning effort on each spawn | `send_input` to the same agent (`resume_agent` reopens a closed one) | `wait_agent` waits for it; do not close the implementer or the reviewer before the run ends. The tools are on by default (`features.multi_agent`) |
| Gemini CLI | the built-in `generalist` subagent (a tool of that name, or `@generalist`), with the prompt | not documented: start a new `generalist` with the handoff below | A subagent does one task and reports back |
| Antigravity | `invoke_subagent` with the prompt | not documented: start a new subagent with the handoff below | |

**The handoff, when a subagent cannot be continued:** start a new one with the same prompt as the first, plus the
new message, plus: "Read `R/progress.md` first: it is the record of the work so far." For a reviewer, add its last
findings file. `progress.md` and the commits hold everything the next agent needs; that is why the implementer
writes them after each ticket.

**Models:** the implementer and the reviewer get your strongest model. The severity pass can run on a smaller one,
or in the controller itself.
