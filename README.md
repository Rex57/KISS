# KISS: Keep It Simple Stupid Workflow harness

A plugin for **Claude Code, Codex, Gemini CLI and Antigravity** that builds a feature with as few agents as the
work needs:

- **one implementer** subagent builds the tickets one at a time;
- **one reviewer** subagent uses the running product (its UI, API or CLI) and reports every issue it finds;
- the controller (your main session) sends each fix back to the **same** implementer.

The input is a short product spec and `tickets.json`. Each ticket has acceptance tests and starts as
`passes: false`. The design follows Anthropic's guidance on long-running harnesses: a feature list, one agent
that works one ticket at a time, and an evaluator that uses the product.

## What is inside

| Skill | What it does |
|---|---|
| `kiss-harness` | Spec, then tickets, then one implementer, then one review that uses the product, then at most 3 fix rounds, then the owner's merge. Its scripts check the tickets, fill the prompts, seed each ticket with CodeGraph and keep the time budget (10 minutes per ticket, plus 2 hours for reviews and fixes). |
| `kiss-tidy-up-memory` | "Tidy up memory": merge and cut an agent's file memory for one repo, run a loss check with a second agent, revise agentmemory (if you use it) and move old transcripts to the Trash. |

How to call a skill:

| Agent | `kiss-harness` | `kiss-tidy-up-memory` |
|---|---|---|
| Claude Code | `/kiss:kiss-harness` | `/kiss:kiss-tidy-up-memory` |
| Codex | `$kiss:kiss-harness`, or pick it in `/skills` | `$kiss:kiss-tidy-up-memory` |
| Gemini CLI | say "build … with the KISS harness" (the model activates it; `/skills list` shows it) | say "tidy up memory" |
| Antigravity | `/kiss-harness` | `/kiss-tidy-up-memory` |

On every agent you can also just say it: "build <feature> with the KISS harness", or "tidy up memory".

## Tools you need

The plugin installs none of these. Install them yourself, once per device.

| Tool | Why | Install |
|---|---|---|
| One of the agents | Runs the skills and the subagents | [Claude Code](https://code.claude.com/docs), [Codex](https://github.com/openai/codex), [Gemini CLI](https://geminicli.com), [Antigravity](https://antigravity.google) |
| git | Worktrees, one commit per ticket | your OS package manager |
| Python 3.9 or later | The scripts (standard library only) | [python.org](https://www.python.org) or [uv](https://docs.astral.sh/uv/) |
| Node.js and npm | CodeGraph runs on Node | [nodejs.org](https://nodejs.org) |
| [CodeGraph](https://github.com/colbymchenry/codegraph) | The ticket seeds, the reviewer's caller checks, the global rule | `npm install -g @colbymchenry/codegraph`, then `codegraph init -y <repo>` in each project |
| [ponytail](https://github.com/DietrichGebert/ponytail) | The smallest complete change per ticket, and the reviewer's rubric F | see "Install ponytail" below |
| `cgcallers` (in this repo) | CodeGraph's callers plus a word grep, before a delete or rename | `install -m 755 skills/kiss-harness/scripts/cgcallers.py ~/.local/bin/cgcallers` (`~/.local/bin` on your `PATH`) |
| A headless browser (optional) | The reviewer uses a web UI | Chrome or Chromium, or Playwright |
| [agentmemory](https://github.com/rohitg00/agentmemory) (optional) | Step 4 of `kiss-tidy-up-memory` | its README |

### Install ponytail

- Claude Code: `/plugin marketplace add DietrichGebert/ponytail`, then `/plugin install ponytail@ponytail`.
- Codex: `codex plugin marketplace add DietrichGebert/ponytail`, then `codex plugin add ponytail@ponytail`. Open
  `/hooks`, trust its two hooks, and start a new thread.
- Gemini CLI, Antigravity and others: follow ponytail's
  [INSTALL.md](https://github.com/DietrichGebert/ponytail/blob/main/INSTALL.md).

## Install KISS

**Claude Code**

```bash
claude plugin marketplace add Rex57/KISS
claude plugin install kiss@kiss
```

In a session, one step (Claude Code 2.1.275 or later): `/plugin install kiss --marketplace Rex57/KISS`.

**Codex** (the CLI; the IDE extension has no plugins)

```bash
codex plugin marketplace add Rex57/KISS
codex plugin add kiss@kiss
```

Then start a new session.

**Gemini CLI**

```bash
gemini extensions install https://github.com/Rex57/KISS
```

**Antigravity**

```bash
git clone https://github.com/Rex57/KISS.git
agy plugin install ./KISS
```

Each agent reads the same `skills/` folder. The manifests are `.claude-plugin/` (Claude Code),
`.codex-plugin/` and `.agents/plugins/marketplace.json` (Codex), `gemini-extension.json` (Gemini CLI) and
`.antigravity-plugin/` (Antigravity).

## The CodeGraph rule: add it to your global instructions

[`rules/codegraph.md`](rules/codegraph.md) tells every agent how to use CodeGraph: which index, a `-p` on every
call, the gaps of `callers`, and how to brief a subagent. Add it once per device to the global instructions file
of each agent you use:

| Agent | Global instructions file | Command (from this repo's folder) |
|---|---|---|
| Claude Code | `~/.claude/CLAUDE.md` | `cat rules/codegraph.md >> ~/.claude/CLAUDE.md` |
| Codex | `~/.codex/AGENTS.md` | `cat rules/codegraph.md >> ~/.codex/AGENTS.md` |
| Gemini CLI and Antigravity | `~/.gemini/GEMINI.md` (both read it) | `cat rules/codegraph.md >> ~/.gemini/GEMINI.md` |

Read the file first: append it once, not again on each update. If `codegraph install` added a
`CODEGRAPH_START`/`CODEGRAPH_END` block to the same file, delete that block.

## Use it in a project

1. Index the repo: `codegraph init -y <repo>`.
2. Copy [`templates/project.md`](skills/kiss-harness/templates/project.md) to `<repo>/.kiss/project.md`, and fill
   it in: how to run and test the project, how to start it for a reviewer, the rules a reviewer checks, and the
   traps.
3. Add `.kiss/runs/` to the repo's `.gitignore` (or `.git/info/exclude`).
4. Ask your agent: "build <feature> with the KISS harness". The skill takes you through the spec and the tickets,
   and asks for your yes before the build, each owner question, the merge and any push.

The whole flow is in [`skills/kiss-harness/SKILL.md`](skills/kiss-harness/SKILL.md). How each agent starts and
continues a subagent is in [`references/agents.md`](skills/kiss-harness/references/agents.md).

## Layout

```
.claude-plugin/              Claude Code manifest and marketplace
.codex-plugin/               Codex manifest
.agents/plugins/             Codex marketplace
.antigravity-plugin/         Antigravity manifest
gemini-extension.json        Gemini CLI manifest
rules/codegraph.md           the CodeGraph rule for the global instructions file
skills/kiss-harness/         SKILL.md, scripts/, templates/, references/
skills/kiss-tidy-up-memory/  SKILL.md
```

Selftests: `python3 -I skills/kiss-harness/scripts/tickets.py --selftest`, the same for `prompt.py` and
`cgcallers.py`.

A new version changes `version` in the four manifests that carry one (`.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, `gemini-extension.json`, `.antigravity-plugin/plugin.json`), and gets a tag `v<version>`.

## License

MIT
