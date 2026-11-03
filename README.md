<p align="center"><img src="assets/kiss-icon.svg" alt="KISS: keep it simple stupid" width="320"></p>

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
| `kiss-harness` | The questions (decisions recorded in `decisions.md`), the spec, the tickets, then one implementer, one review that uses the product, at most 3 fix rounds, and the owner's merge. Its scripts check the tickets, fill the prompts, seed each ticket with CodeGraph and keep the time budget (10 minutes per ticket, plus 2 hours for reviews and fixes). |
| `kiss-doctor` | Checks a device for a run: the CodeGraph rule in each agent's global instructions file, the skills KISS calls (installed, enabled, once, callable by the model) and the tools. It reports each problem with its fix and installs nothing. |
| `kiss-mini-agent` | A small side task in a background worker: a code change on its own `mini/<id>` branch, a read-only question, or a watch on a pull request, a CI run or a test command. kiss-harness hands off work outside its tickets to it. On Claude Code a mod adds `/mini` (`/mini <task>`, `/mini --now <task>` to skip the worker's checks, `/mini ask <question>`, `/mini watch pr <n>` / `run <id>` / `<test command>`, `/mini stop <id>`, `/mini status`, `/mini` alone opens the pane), a band with the counts, and the delivery buttons (Merge into the base, Push, Draft PR, Discard); only your press delivers. |
| `kiss-housekeeping` | "Clean up the docs": a First run, on your ask, gives each fact one home, sorts pages by kind (living, log, record, history), builds a map, retires stale pages, fixes old names, moves files without breaking code or tests, installs a docs gate in your tests (`tools/check_docs.py`, your own copy) and proves the result with a routing test. After that, each harness close runs its Upkeep when your facts file names the gate. |
| `kiss-tidy-up-memory` | "Tidy up memory": merge and cut an agent's file memory for one repo, run a loss check with a second agent, revise agentmemory (if you use it) and move old transcripts to the Trash. |

How to call a skill:

| Agent | `kiss-harness` | `kiss-doctor` | `kiss-tidy-up-memory` | `kiss-housekeeping` | `kiss-mini-agent` |
|---|---|---|---|---|---|
| Claude Code | `/kiss:kiss-harness` | `/kiss:kiss-doctor` | `/kiss:kiss-tidy-up-memory` | `/kiss:kiss-housekeeping` | `/mini <task>` (the mod), or `/kiss:kiss-mini-agent <task>` |
| Codex | `$kiss:kiss-harness`, or pick it in `/skills` | `$kiss:kiss-doctor` | `$kiss:kiss-tidy-up-memory` | `$kiss:kiss-housekeeping` | `$kiss:kiss-mini-agent <task>` |
| Gemini CLI | say "build … with the KISS harness" (the model activates it; `/skills list` shows it) | say "kiss doctor" | say "tidy up memory" | say "clean up the docs" | say "mini task: <task>" |
| Antigravity | `/kiss-harness` | `/kiss-doctor` | `/kiss-tidy-up-memory` | `/kiss-housekeeping` | `/kiss-mini-agent <task>` |

On every agent you can also just say it: "build <feature> with the KISS harness", "clean up the docs", or "tidy up memory".
`kiss-doctor` starts only when you call it.

## Tools you need

The plugin installs none of these. Install them yourself, once per device, then run `kiss-doctor`: it checks
each one.

| Tool | Why | Install |
|---|---|---|
| One of the agents | Runs the skills and the subagents | [Claude Code](https://code.claude.com/docs), [Codex](https://github.com/openai/codex), [Gemini CLI](https://geminicli.com), [Antigravity](https://antigravity.google) |
| git | Worktrees, one commit per ticket | your OS package manager |
| Python 3.9 or later | The scripts (standard library only) | [python.org](https://www.python.org) or [uv](https://docs.astral.sh/uv/) |
| Node.js and npm | CodeGraph runs on Node | [nodejs.org](https://nodejs.org) |
| [CodeGraph](https://github.com/colbymchenry/codegraph) | The ticket seeds, the reviewer's caller checks, the global rule | `npm install -g @colbymchenry/codegraph`, then `codegraph init -y <repo>` in each project |
| [ponytail](https://github.com/DietrichGebert/ponytail) | `ponytail`: the smallest complete change per ticket and the reviewer's rubric F; `ponytail-review`: the reviewer's rubric G (risk, load, speed); `ponytail-debt`: the list of new `shortcut:` comments at the close | see "Install ponytail" below |
| [Matt Pocock's skills](https://github.com/mattpocock/skills) | `grilling`: the questions; `domain-modeling`: a glossary and ADRs, when the project turns domain docs on; `tdd`: the implementer's red-green loop; `codebase-design` and `prototype`: step 1, for an interface change and a decision the owner can try; `diagnosing-bugs`: the implementer, a failure it cannot explain; `pr`: a pull request body at the push gate | see "Install Matt Pocock's skills" below |
| `cgcallers` (in this repo) | CodeGraph's callers plus a word grep, before a delete or rename | `install -m 755 skills/kiss-harness/scripts/cgcallers.py ~/.local/bin/cgcallers` (`~/.local/bin` on your `PATH`) |
| A headless browser (optional) | The reviewer uses a web UI | Chrome or Chromium, or Playwright |
| [agentmemory](https://github.com/rohitg00/agentmemory) (optional) | Step 4 of `kiss-tidy-up-memory` | its README |

### Install ponytail

- Claude Code: `/plugin marketplace add DietrichGebert/ponytail`, then `/plugin install ponytail@ponytail`.
- Codex: `codex plugin marketplace add DietrichGebert/ponytail`, then `codex plugin add ponytail@ponytail`. Open
  `/hooks`, trust its two hooks, and start a new thread.
- Gemini CLI, Antigravity and others: follow ponytail's
  [INSTALL.md](https://github.com/DietrichGebert/ponytail/blob/main/INSTALL.md).

### Install Matt Pocock's skills

KISS uses seven of them: `grilling`, `domain-modeling`, `tdd`, `codebase-design`, `prototype`, `diagnosing-bugs` and
`pr`. Install them once per agent, in one way only:
two installs give you every skill twice. KISS needs no `/setup-matt-pocock-skills`, because it does not use his
issue-tracker skills.

- Claude Code (updates itself):

  ```bash
  claude plugin install mattpocock-skills@claude-plugins-official
  ```

- Codex (updates itself at startup):

  ```bash
  codex plugin marketplace add mattpocock/skills
  codex plugin add mattpocock-skills@mattpocock
  ```

- Gemini CLI (run both again to update):

  ```bash
  gemini skills install https://github.com/mattpocock/skills.git --path skills/engineering
  gemini skills install https://github.com/mattpocock/skills.git --path skills/productivity
  ```

- Antigravity: his README has no steps for it. Copy the skill folders into Antigravity's global skills folder,
  `~/.gemini/config/skills/` (App and IDE) or `~/.gemini/antigravity-cli/skills/` (CLI), and copy them again to
  update:

  ```bash
  git clone https://github.com/mattpocock/skills.git mattpocock-skills
  mkdir -p ~/.gemini/config/skills
  cp -R mattpocock-skills/skills/productivity/grilling mattpocock-skills/skills/engineering/domain-modeling \
        mattpocock-skills/skills/engineering/tdd mattpocock-skills/skills/engineering/codebase-design \
        mattpocock-skills/skills/engineering/prototype mattpocock-skills/skills/engineering/diagnosing-bugs \
        mattpocock-skills/skills/engineering/pr ~/.gemini/config/skills/
  ```

### User-only skills

A user-only skill has `disable-model-invocation: true` in its frontmatter: only you can start it (its slash command
or its name), and the model cannot call it. KISS cannot call such a skill for you, so `kiss-doctor` fails a skill
KISS calls that is user-only: install it again from its source (above), or delete that line from your own copy of
it. KISS's own skills that you start now and then (such as `kiss-doctor`) are user-only on purpose.

If a skill is missing, a run still works: KISS follows its own copy of the same rules
([`references/spec-and-tickets.md`](skills/kiss-harness/references/spec-and-tickets.md) and its prompts), and
`decisions.md` records which skills the run used.

## How a run goes

1. **Questions.** The controller settles every open decision with you, in rounds, each numbered `D<n>` with its
   recommended answer (Matt Pocock's `grilling` when installed). Each answer goes into `decisions.md` at once.
   Only a choice that is costly to undo is a question; a two-way door (a name, a default you can change later)
   takes the recommended answer, and you see it at the tickets gate.
2. **Spec and tickets**, by rules adapted from Matt Pocock's `to-spec` and `to-tickets`: user stories, test seams,
   thin slices through every layer, a refactor first, blocking links. Each acceptance line names its seam. You
   approve the tickets and the seams.
3. **Build:** one implementer, one ticket at a time, with ponytail and `tdd`. Each ticket ends with what it skipped
   and any risk.
4. **Review:** one reviewer uses the running product, with rubric A to G (`ponytail-review` for risk, load and
   speed). A severity pass sorts the findings; the same implementer fixes them and the same reviewer checks again,
   at most 3 rounds.
5. **Close:** the project's full check, a look back at the run (each mistake becomes a proposed check or a rule, on your yes), the list of new `shortcut:` comments (`ponytail-debt`), the docs Upkeep
   (`kiss-housekeeping`) when `.kiss/project.md` names a docs gate (with no `Docs gate:` line it asks you once
   whether to do a docs First run, and records a no), and the merge gate: one yes, or none when `.kiss/project.md` says `Merge: after a green close`. A push always asks.

The controller asks you two kinds of thing. A **decision** (`D<n>`) is a choice about the product, its data, its
interfaces or its tests, and goes into `decisions.md`. A **gate** (the tickets, more rounds, the budget, the
merge, a push) is a go or no-go with its evidence, and has no number. Routine steps (the branch, a commit per
ticket, the docs) are not questions.

Matt Pocock's `code-review` is not part of a run: the reviewer and `ponytail-review` cover it.

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
2. On the first run, the controller drafts `<repo>/.kiss/project.md` from the repo (from
   [`templates/project.md`](skills/kiss-harness/templates/project.md)) and asks you only about the gaps: how to run
   and test the project, how to start it for a reviewer, the rules a reviewer checks, the traps, and whether
   domain docs (a glossary and ADRs) are on.
3. Add `.kiss/runs/` to the repo's `.gitignore` (or `.git/info/exclude`).
4. Ask your agent: "build <feature> with the KISS harness". The skill takes you through the spec and the tickets,
   asks you each decision, and waits for your yes at each gate: the tickets, the merge and any push.

The whole flow is in [`skills/kiss-harness/SKILL.md`](skills/kiss-harness/SKILL.md). How each agent starts and
continues a subagent is in [`references/agents.md`](skills/kiss-harness/references/agents.md).

## Feedback mode

Off by default. When it is on, every KISS skill ends its run with one **KISS feedback** block: the skill and the
KISS version, what went wrong or was unclear, and each proposed change as a KISS file, a line and the new text. The
block holds no name, path, code, data or secret of your project. The rule is [`rules/feedback.md`](rules/feedback.md).

Turn it on with the environment variable `KISS_FEEDBACK=1`, in one of two places:

- your shell profile (every agent reads it): `export KISS_FEEDBACK=1`;
- Claude Code's `~/.claude/settings.json`: `"env": { "KISS_FEEDBACK": "1" }`.

Unset it, or set any other value, to turn it off. Post the block as an issue on the KISS repo with the
[KISS feedback template](https://github.com/Rex57/KISS/issues/new?template=kiss-feedback.md), or paste it into an
agent session in a KISS checkout to apply it. Read it before you post: the repo is public.

In Claude Code's default permission mode, the first block asks once to read the KISS rule file and the
manifest: they sit outside your project.

## Layout

```
.claude-plugin/              Claude Code manifest and marketplace
.codex-plugin/               Codex manifest
.agents/plugins/             Codex marketplace
.antigravity-plugin/         Antigravity manifest
gemini-extension.json        Gemini CLI manifest
rules/codegraph.md           the CodeGraph rule for the global instructions file
rules/feedback.md            the feedback mode: the block each skill ends with when KISS_FEEDBACK=1
.github/ISSUE_TEMPLATE/      the issue template for a KISS feedback block
skills/kiss-harness/         SKILL.md, scripts/, templates/, references/
skills/kiss-doctor/          SKILL.md, scripts/doctor.py
skills/kiss-tidy-up-memory/  SKILL.md
skills/kiss-housekeeping/    SKILL.md, standard.md, moves.md, routing.md, scripts/ (the docs gate, inventory, mover)
skills/kiss-mini-agent/      SKILL.md, references/handoff.md (the brief, the report, the worker's rules)
mods/kiss-mini-agent/        the Claude Code mod: /mini, the background host, the band and the pane (Claude Code only)
claude-agents/               kiss-implementer, kiss-reviewer and kiss-worker, the named subagents (Claude Code)
```

Selftests: `python3 -I skills/kiss-harness/scripts/tickets.py --selftest`, the same for `prompt.py`,
`cgcallers.py`, `skills/kiss-doctor/scripts/doctor.py` and the three scripts in `skills/kiss-housekeeping/scripts/`. The mod's tests: `claude plugin test .`.

A new version changes `version` in the four manifests that carry one (`.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, `gemini-extension.json`, `.antigravity-plugin/plugin.json`), and gets a tag `v<version>`.

## License

MIT
