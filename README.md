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

## Why KISS: proven skills, one daily workflow

KISS does not rebuild what other projects already do well. Matt Pocock's skills, ponytail and CodeGraph are
mature and proven in real work. KISS is the workflow that joins them into one development lifecycle, from the
first idea to the upkeep of a running project:

| Phase | KISS skill | What it brings in |
|---|---|---|
| Design | `kiss-system-design`, then step 1 of `kiss-harness` | `grilling`, `domain-modeling`, `codebase-design`, `prototype`, `research` |
| Build | `kiss-harness`, with `kiss-mini` for side tasks | `tdd`, `diagnosing-bugs`, `ponytail`, CodeGraph, `pr` |
| Review | the reviewer of `kiss-harness` | `ponytail-review`, CodeGraph callers |
| Clean | `kiss-code-clean`, `kiss-housekeeping` | `ponytail-audit`, `ponytail-debt`, CodeGraph |
| Maintain | `kiss-dream`, `kiss-doctor`, the docs Upkeep | agentmemory (optional) |

How KISS uses them:

- **Call, do not copy.** KISS calls each skill at the step where it fits. From a skill that only you can start,
  KISS copies the rules alone, with the license notice ([`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)), so a
  run works the same when that skill is not installed.
- **The step knows the skill.** Each step names the skill it uses, so you do not have to remember which one comes
  next.
- **In step with upstream.** The owner's `kiss-check-update` (in this repo only, not in the plugin) compares every
  source with its latest release, so each KISS release matches the newest versions.

What KISS adds:

- **Few agents.** One implementer and one reviewer per run, not one agent per ticket: fewer tokens, and each fix
  goes back to the agent that has the context.
- **Proof in the running product.** The reviewer uses the product (its UI, API or CLI), not only the diff, and
  each ticket has acceptance tests that name their seam.
- **No missed caller.** Every agent reads the code through CodeGraph first, and each subagent gets CodeGraph's
  output in its seed file. CodeGraph's `callers` misses some calls: the measured blind spots are in the
  [CodeGraph rule](rules/codegraph.md) ("`callers` is incomplete"). So before a delete, rename or signature change,
  the implementer and the reviewer run `cgcallers`, and `callcheck.py` runs it on each function the staged diff (or
  a range of commits) removes, renames or re-signs. `cgcallers` syncs the index, shows each definition of the name
  in its own block, and puts CodeGraph's callers beside a word search of the files that import the function's module
  or package (every file for a method; comments and strings left out, but not a name given to `getattr` as a
  string). It marks each call that CodeGraph missed (`[grep only]`) and each edge CodeGraph only guessed from the
  name (`[cg guess]`). With `pyright` (Python) or `typescript-language-server` (JS/TS) on your `PATH`, its LSP pass
  asks that server for the references and marks each one CodeGraph did not list `[lsp]` (a method on a typed object,
  for example); with no server it says that the pass was skipped.
- **You decide.** Only a choice that is costly to undo becomes a question (`D<n>`, kept in `decisions.md`). A gate
  (the tickets, the merge, a push) asks for your go with its evidence. Nothing is pushed without you.
- **Safety in code.** A guard that protects your data is a script with a selftest, not an instruction the model
  must remember: for example `kiss-dream`'s memory guard and the feedback switch.
- **Four agents, one plugin:** Claude Code, Codex, Gemini CLI and Antigravity.
- **Used every day.** The author uses these workflows every day for real development work, and refines them
  continuously. Turn on the [feedback mode](#feedback-mode) to tell us what to improve.

## What is inside

| Skill | What it does |
|---|---|
| `kiss-harness` | The questions (decisions recorded in `decisions.md`), the spec, the tickets, then one implementer, one review that uses the product, at most 2 fix rounds per review and 3 per run, a metrics line, and the owner's merge. Its scripts check the tickets, fill the prompts, seed each ticket with CodeGraph and keep the time budget (10 minutes per ticket, plus 2 hours for reviews and fixes, plus the full check time from the facts file). |
| `kiss-doctor` | Checks a device for a run: the CodeGraph rule in each agent's global instructions file, the skills KISS calls (installed, enabled, once, callable by the model) and the tools. It reports each problem with its fix. `kiss-doctor setup` shows a numbered plan of what is missing, and KISS installs only on your request, from the official sources, after you see each command. |
| `kiss-mini` | A small side task in a background worker: a code change on its own `mini/<id>` branch, a read-only question, or a watch on a pull request, a CI run or a test command. kiss-harness hands off work outside its tickets to it. On Claude Code a mod answers `/kiss-mini` (`/kiss-mini <task>`, `/kiss-mini --now <task>` to skip the worker's checks, `/kiss-mini ask <question>`, `/kiss-mini watch pr <n>` / `run <id>` / `<test command>`, `/kiss-mini stop <id>`, `/kiss-mini status`, `/kiss-mini` alone opens the pane), a band with the counts, and the delivery buttons (Merge into the base, Push, Draft PR, Discard); only your press delivers. |
| `kiss-housekeeping` | "Clean up the docs": a First run, on your ask, gives each fact one home, sorts pages by kind (living, log, record, history), builds a map, retires stale pages, fixes old names, moves files without breaking code or tests, installs a docs gate in your tests (`tools/check_docs.py`, your own copy) and proves the result with a routing test. After that, each harness close runs its Upkeep when your facts file names the gate. |
| `kiss-system-design` | First version. From a new product idea to a plan of harness runs: a product brief, a decision map (decisions so far, open decisions typed research / prototype / grilling / task, not yet clear, out of scope), one decision at a time with you (research in the background), then a system design document and an ordered run plan in your docs. Its working files stay in the git-ignored `.kiss/design/<name>/`; continue a design by its name. An idea that fits one run goes to `kiss-harness`. |
| `kiss-code-clean` | "Clean up the code": one ranked list of clean-up candidates for a code base (bugs, risky code with no test, slow paths, code to delete, merge or split, `shortcut:` debt, hot spots from the git history), each with its evidence and a strength, saved in `.kiss/clean/<date>.md`. A delete candidate shows that nothing uses it (CodeGraph and a word search). It changes no code: you pick, and each pick becomes a harness run or a `/kiss-mini` task. |
| `kiss-dream` | "Tidy up memory": on your ask (unlike Claude Code's background auto-dream), merge and cut an agent's file memory for one repo, run a loss check with a second agent, revise agentmemory (if you use it) and move old transcripts to the Trash. "Tidy up memory" or its command starts the whole flow; other words get the plan first. When another consolidation holds the memory folder's lock, it stops, writes no note and asks you to run it again; its report starts with one row per step. A memory gate (`scripts/check_memory.py`) checks the notes and the index, and a recall test (fresh readers answer questions from the old notes, scored found, wrong or not found) proves nothing was lost. |

How to call a skill:

| Agent | `kiss-harness` | `kiss-doctor` | `kiss-dream` | `kiss-housekeeping` | `kiss-code-clean` | `kiss-system-design` | `kiss-mini` |
|---|---|---|---|---|---|---|---|
| Claude Code | `/kiss:kiss-harness` | `/kiss:kiss-doctor` | `/kiss:kiss-dream` | `/kiss:kiss-housekeeping` | `/kiss:kiss-code-clean` | `/kiss:kiss-system-design [<name>]` | `/kiss-mini <task>` (or `/kiss:kiss-mini <task>`; the mod answers it) |
| Codex | `$kiss:kiss-harness`, or pick it in `/skills` | `$kiss:kiss-doctor` | `$kiss:kiss-dream` | `$kiss:kiss-housekeeping` | `$kiss:kiss-code-clean` | `$kiss:kiss-system-design [<name>]` | `$kiss:kiss-mini <task>` |
| Gemini CLI | say "build … with the KISS harness" (the model activates it; `/skills list` shows it) | say "kiss doctor" | say "tidy up memory" | say "clean up the docs" | say "kiss code clean" | say "kiss system design" | say "mini task: <task>" |
| Antigravity | `/kiss-harness` | `/kiss-doctor` | `/kiss-dream` | `/kiss-housekeeping` | `/kiss-code-clean` | `/kiss-system-design [<name>]` | `/kiss-mini <task>` |

On every agent you can also just say it: "build <feature> with the KISS harness", "clean up the docs", or "tidy up memory".
`kiss-doctor`, `kiss-code-clean` and `kiss-system-design` start only when you call them.

## Tools you need

KISS installs only on your request, from the official sources, after you see each command. Run
`kiss-doctor setup` (`/kiss:kiss-doctor setup` in Claude Code): it finds your OS, shell, package manager and the
agents on your PATH, and shows a numbered plan of what is missing, each item with its command, its source and what
it changes. You answer all, none or the numbers: it installs those, one at a time, stops at the first failure,
runs the checks again and lists the steps only you can do. It never runs `sudo` and never edits your shell profile:
it shows those lines for you to run. Name agents to set up only those (`kiss-doctor setup claude`). The plan also
offers two optional kinds of item: the language servers for `cgcallers`' LSP pass (only for a language your repo has
files of), and CodeGraph's MCP server for each agent, added through the agent's own command (Claude Code also gets the
permission `mcp__codegraph__*`; Antigravity: a step by hand). It never runs `codegraph install`. Or install each tool
yourself from its link, once per device, then run `kiss-doctor`: it checks each one.

| Tool | Why | Install |
|---|---|---|
| One of the agents | Runs the skills and the subagents | [Claude Code](https://code.claude.com/docs), [Codex](https://github.com/openai/codex), [Gemini CLI](https://geminicli.com), [Antigravity](https://antigravity.google) |
| git | Worktrees, one commit per ticket | `kiss-doctor setup` (your package manager), or [git-scm.com](https://git-scm.com/downloads) |
| Python 3.9 or later | The scripts (standard library only) | `kiss-doctor setup` (your package manager), or [python.org](https://www.python.org) or [uv](https://docs.astral.sh/uv/) |
| Node.js and npm | CodeGraph runs on Node | `kiss-doctor setup` (your package manager), or [nodejs.org](https://nodejs.org) |
| [CodeGraph](https://github.com/colbymchenry/codegraph) | The ticket seeds, the reviewer's caller checks, the global rule | `kiss-doctor setup`, or `npm install -g @colbymchenry/codegraph`, then `codegraph init -y <repo>` in each project |
| [ponytail](https://github.com/DietrichGebert/ponytail) | `ponytail`: the smallest complete change per ticket and the reviewer's rubric F; `ponytail-review`: the reviewer's rubric G (risk, load, speed); `ponytail-debt`: the list of new `shortcut:` comments at the close; `ponytail-audit` and `ponytail-debt`: `kiss-code-clean`'s audit report and debt ledger | `kiss-doctor setup`, or see "Install ponytail" below |
| [Matt Pocock's skills](https://github.com/mattpocock/skills) | `grilling`: the questions; `domain-modeling`: a glossary and ADRs, when the project turns domain docs on; `tdd`: the implementer's red-green loop; `codebase-design` and `prototype`: step 1, for an interface change and a decision the owner can try; `diagnosing-bugs`: the implementer, a failure it cannot explain; `pr`: a pull request body at the push gate; `research`: `kiss-system-design`'s research decisions (`kiss-doctor` does not check `research`) | `kiss-doctor setup`, or see "Install Matt Pocock's skills" below |
| `cgcallers` (in this repo) | CodeGraph's callers plus a word search of the importing files, before a delete or rename | `kiss-doctor setup` (into `~/.local/bin`, or the folder `KISS_BIN` names), or `install -m 755 skills/kiss-harness/scripts/cgcallers.py ~/.local/bin/cgcallers` (that folder on your `PATH`) |
| [pyright](https://github.com/microsoft/pyright) (optional) | `cgcallers`' LSP pass for Python | `kiss-doctor setup` (for a repo with Python files), or `npm install -g pyright` |
| [typescript-language-server](https://github.com/typescript-language-server/typescript-language-server) (optional) | `cgcallers`' LSP pass for JS/TS (it needs TypeScript 5 or 6: TypeScript 7 has no `tsserver.js`) | `kiss-doctor setup` (for a repo with JS/TS files), or `npm install -g typescript-language-server typescript@5` |
| CodeGraph's MCP server (optional) | CodeGraph's tools in any session of each agent, without KISS | `kiss-doctor setup` (each agent's own `mcp add`: `claude mcp add --scope user codegraph -- codegraph serve --mcp` and the permission `mcp__codegraph__*`; `codex mcp add codegraph -- codegraph serve --mcp`; `gemini mcp add --scope user codegraph codegraph serve --mcp`; Antigravity: by hand in its MCP settings) |
| A headless browser (optional) | The reviewer uses a web UI | Chrome or Chromium, or Playwright |
| [agentmemory](https://github.com/rohitg00/agentmemory) (optional) | Step 4 of `kiss-dream` | its README |

### Install ponytail

`kiss-doctor setup` installs it for each agent on your PATH (Codex: then open `/hooks`, trust its two hooks and
start a new thread; Antigravity: by hand). Upstream steps: [INSTALL.md](https://github.com/DietrichGebert/ponytail/blob/main/INSTALL.md).

### Install Matt Pocock's skills

KISS uses eight of them: `grilling`, `domain-modeling`, `tdd`, `codebase-design`, `prototype`, `diagnosing-bugs`,
`pr` and `research`. Install them once per agent, in one way only: two installs give you every skill twice. KISS
needs no `/setup-matt-pocock-skills`, because it does not use his issue-tracker skills.

`kiss-doctor setup` installs them for each agent on your PATH (Antigravity: copy the eight skill folders from a
clone into `~/.gemini/config/skills/`, by hand). Upstream steps: [mattpocock/skills](https://github.com/mattpocock/skills).

### User-only skills

A user-only skill has `disable-model-invocation: true` in its frontmatter: only you can start it (its slash command
or its name), and the model cannot call it. KISS cannot call such a skill for you, so `kiss-doctor` fails a skill
KISS calls that is user-only: install it again from its source (above), or delete that line from your own copy of
it. KISS's own skills that you start now and then (such as `kiss-doctor`, `kiss-code-clean` and `kiss-system-design`) are user-only on purpose.

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
   answer the test seams once, as a decision, and approve the tickets.
3. **Build:** one implementer, one ticket at a time, with ponytail and `tdd`, in a worktree under the git-ignored
   `.kiss/worktrees/`. Each ticket ends with what it skipped
   and any risk.
4. **Review:** one reviewer uses the running product, with rubric A to G (`ponytail-review` for risk, load and
   speed). The controller sorts the findings: a wrong result, a broken command or link, data, security, a guard or
   a rule of yours is always fixed; a low finding with no effect on a user, data or a rule goes to the log, which
   you see at the merge gate. The same implementer fixes each one and names the test that failed before and passes
   now; the controller checks those, and the same reviewer rechecks in the product only critical, high or
   reproduced findings. At most 2 fix rounds per review and 3 per run, then a gate (none when only low or medium
   findings that touch no guard, data or rule of yours are left: the merge gate offers them as one `/kiss-mini`
   task). A risky ticket gets its own review only when it guards real data or later tickets build on its guard;
   meanwhile the implementer builds the tickets that do not depend on it.
5. **Close:** the project's full check, one metrics line (subagents, fix rounds, rechecks, headless sessions,
   minutes against the budget, and on Claude Code the tokens per role and the CodeGraph share against code searches, with a grep after a
   pipe or on docs or data counted apart), recorded one line
   per run in `.kiss/metrics.md`, a look back at the run (each mistake becomes a proposed check or a rule, on your yes), the list of new `shortcut:` comments (`ponytail-debt`), the docs Upkeep
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

**Then, after the first install and after each KISS update, run `kiss-doctor setup`** (Claude Code:
`/kiss:kiss-doctor setup`; Codex: `$kiss:kiss-doctor setup`; Gemini CLI: say "kiss doctor setup"; Antigravity:
`/kiss-doctor setup`). A new version can call a new skill or tool: setup shows what your device lacks and installs only
what you approve (see "Tools you need").

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

`kiss-doctor setup` appends it for you, on your answer. Read the file first: append it once, not again on each update. If `codegraph install` added a
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

Turn it on with the environment variable `KISS_FEEDBACK=1`, in one of these places, never in the plugin's own files
(that would turn it on for every user):

- Claude Code's `~/.claude/settings.json`, for every Claude Code session: `"env": { "KISS_FEEDBACK": "1" }`;
- your shell profile, for every agent: `export KISS_FEEDBACK=1`;
- a project's `.claude/settings.local.json`, for that project only: `"env": { "KISS_FEEDBACK": "1" }`.

`kiss-doctor` reports the mode and where it is set in every run. `kiss-doctor feedback on` and
`kiss-doctor feedback off` set it in Claude Code's user settings (`"1"` or `"0"`, so off wins over a shell
profile), with a timestamped backup beside the file at each switch; for the other agents it prints the export line for your shell profile.

Unset it, or set any other value, to turn it off. Each skill's last line runs `rules/feedback.py` when the skill
loads (a Claude Code inline command): with the mode off it prints nothing, so the skill has no feedback step and the
run makes no feedback call; with it on it prints the step with the rule and the KISS version, so the run reads no
file outside your project. The other agents run the same command at the end of the run. A policy that disables
skill shell execution (`disableSkillShellExecution`) turns the mode off.

Post the block as an issue on the KISS repo with the
[KISS feedback template](https://github.com/Rex57/KISS/issues/new?template=kiss-feedback.md), or paste it into an
agent session in a KISS checkout to apply it. Read it before you post: the repo is public.

## Layout

```
.claude-plugin/              Claude Code manifest and marketplace
.codex-plugin/               Codex manifest
.agents/plugins/             Codex marketplace
.antigravity-plugin/         Antigravity manifest
gemini-extension.json        Gemini CLI manifest
rules/codegraph.md           the CodeGraph rule for the global instructions file
LICENSE, NOTICE              Apache-2.0 and the author credit; THIRD_PARTY_NOTICES.md: Matt Pocock's MIT license
rules/feedback.md            the feedback mode: the block each skill ends with when KISS_FEEDBACK=1
rules/feedback.py            prints a skill's feedback step, only when KISS_FEEDBACK=1
.github/ISSUE_TEMPLATE/      the issue template for a KISS feedback block
skills/kiss-harness/         SKILL.md, scripts/, templates/, references/
skills/kiss-doctor/          SKILL.md, scripts/doctor.py
skills/kiss-dream/           SKILL.md, scripts/guard.py (the guarded write), scripts/check_memory.py (the memory gate)
skills/kiss-code-clean/      SKILL.md, references/architecture.md
skills/kiss-system-design/   SKILL.md, references/map.md (the map and decision file formats)
skills/kiss-housekeeping/    SKILL.md, standard.md, moves.md, routing.md, scripts/ (the docs gate, inventory, mover)
skills/kiss-mini/            SKILL.md, references/handoff.md (the brief, the report, the worker's rules)
.claude/skills/kiss-check-update/  the KISS owner's tool, not part of the plugin: checks each upstream source
                             (Matt Pocock's skills, ponytail, CodeGraph, the mods API) against its record, upstream.json
mods/kiss-mini/              the Claude Code mod: /kiss-mini, the background host, the band and the pane (Claude Code only)
claude-agents/               kiss-implementer, kiss-reviewer and kiss-worker, the named subagents (Claude Code)
```

Selftests: `python3 -I skills/kiss-harness/scripts/tickets.py --selftest`, the same for `prompt.py`, `briefs.py`, `callcheck.py`, `metrics.py`,
`cgcallers.py`, `skills/kiss-doctor/scripts/doctor.py`, `skills/kiss-dream/scripts/guard.py`, `check_memory.py`, `.claude/skills/kiss-check-update/scripts/check_update.py`, `rules/feedback.py` and the three scripts in `skills/kiss-housekeeping/scripts/`. The mod's tests: `claude plugin test .`.

A new version changes `version` in the four manifests that carry one (`.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, `gemini-extension.json`, `.antigravity-plugin/plugin.json`), and gets a tag `v<version>`.

## License

Apache License 2.0 ([`LICENSE`](LICENSE)), from the release after v1.0.1; releases up to v1.0.1 stay under the MIT
License. The author is Nanami (Rex57): every copy and derivative must keep [`NOTICE`](NOTICE) with that credit.
When KISS helped you build something, a mention is welcome (not required). The rules adapted from Matt Pocock's
skills keep his MIT license: [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
