---
name: kiss-code-clean
description: A ranked list of clean-up candidates for a code base (bugs, risky untested code, slow paths, code to delete, merge or split, shortcut debt, hot spots), each with its evidence. Reads only.
disable-model-invocation: true
allowed-tools: Bash(python3 -I "${CLAUDE_PLUGIN_ROOT}/rules/feedback.py" *)
---

# KISS code clean

You find what to clean up in a code base and rank it; the owner picks, and each pick is built later by kiss-harness
or kiss-mini. `CC` is this skill's folder (the folder of this file). The scope is the repo, or the folder the
owner names.

You read the code, the git history and the tools' output, and you show a bug from the code: its file, its line and
the input that breaks it. You never run the repo's code, its tests, its scripts or its build (no `pytest`, no
`python app.py`, no `npm test`, no import of its modules): a run can change its data. You delete no file and change
no tracked file; your one write is the list in the git-ignored `.kiss/clean/` (step 7).

## Skills it uses when they are installed

| Skill | From | Used in | Without it |
|---|---|---|---|
| `ponytail-audit` | ponytail | step 3, the audit | the entry points and the hot spots read by you |
| `ponytail-debt` | ponytail | step 4, the debt | `git grep -n "shortcut:"` |
| `codebase-design` | Matt Pocock's skills | step 5, the architecture: its words and its deepening check | the rules in [references/architecture.md](references/architecture.md) alone |

## Steps

1. **Check the tools.** Record `git -C "<repo>" status --short` as it is now: step 7 compares with it. In your skill
   list: the skills of the table above; Claude Code and
   Codex name them `ponytail:ponytail-audit`, `ponytail:ponytail-debt` and `mattpocock-skills:codebase-design`. Each
   one your list shows is called with the Skill tool, by that full name, in its step (3, 4, 5): a missing CodeGraph
   or a small repo skips none of them, and reading the code yourself is no substitute. On the shell:
   `codegraph status "<repo>"` prints `Project: <repo>` and no `Not initialized` line (the repo is indexed), and
   `$CC/../kiss-harness/scripts/cgcallers.py` exists. Note each skill or tool that is missing; step 7 names the part
   it skipped. Done when each one is found or noted.
2. **Hot spots.** `git -C "<repo>" log --since="6 months ago" --name-only --format=` and count the changes per file:
   the top ten are the hot spots. A candidate in a hot spot ranks higher (a clean-up there pays off soonest). No
   history: say so. Done when the list is written down.
3. **Audit.** Load `ponytail-audit` on the scope: its ranked report (bugs, security, load, risky code with no test,
   slow paths, what to delete, merge or split) gives the first candidates, each with its file, line and reason.
   Without it, read the entry points and the hot spots yourself for the same kinds. Done when each finding has its
   file and line.
4. **Debt.** Load `ponytail-debt` on the scope: each `shortcut:` comment is a candidate with its limit. Without it,
   `git -C "<repo>" grep -n "shortcut:"`. Done when every `shortcut:` line is listed.
5. **Architecture.** Call the Skill tool with `mattpocock-skills:codebase-design` first, also when you expect no
   candidate. Then look for deepening by the rules in [references/architecture.md](references/architecture.md),
   hot spots first, in `codebase-design`'s words (module, interface, depth, seam, adapter, leverage, locality). Give
   each candidate a strength: `Strong`, `Worth exploring` or `Speculative`. Done when each has its strength.
6. **The delete check.** A delete candidate is code that nothing uses. Before you list one, prove it for each
   symbol: `codegraph callers -p "<repo>" <name>` (widen a cut list with `--limit`), `codegraph impact -p "<repo>"
   <name>`, and `python3 -I "$CC/../kiss-harness/scripts/cgcallers.py" <name> -p "<repo>"`; read every
   `[grep only]` line. Then a word search of the whole repo, `git -C "<repo>" grep -nw <name>`, for a use CodeGraph
   cannot see: a string (a `getattr`, a registry or route table, a dispatch by name, a config file), a test, a doc.
   A name can be built at run time (`getattr(mod, "cmd_" + name)`, `globals()[...]`, `importlib`, a decorator that
   registers it): search the module's users for such a lookup and for the name's prefix or suffix (`"cmd_"`); a
   lookup that can reach the symbol is a use.
   Any caller, route, test, string or doc use: it is not a delete candidate (list it as a merge or rename candidate
   only when that holds). Without CodeGraph: list no delete candidate, and say so. Done when each delete candidate
   shows its callers, impact, cgcallers and word-search results, all empty but its own definition.
7. **One ranked list.** Join every candidate into one list; the script sorts it, never you: by kind first, in this
   order: (1) `bug` or `security`, (2) `risky` (code with no test), (3) `load` or `slow`, (4) `delete`, `merge`,
   `split` or `deepen`, (5) `shortcut` debt; then by strength, `Strong`, `Worth exploring`, `Speculative`; at equal
   strength a hot spot first. Every row gets one of those kinds and strengths, a `shortcut:` with a named trigger too.
   Each row: kind, `file:line` (`where`), the evidence (the check that found it and its result), the strength, the
   build it needs (a harness run for a change across modules or an interface, a `/kiss-mini` task for a small local
   one) and `hot` (true for a hot spot). The skipped lines start the list: one per skill or tool that step 1 found
   missing ("ponytail not installed: no audit report, no debt ledger"), and one per installed skill of steps 3 to 5
   that the run did not call. Write them as JSON to a temp file outside the repo,
   `{"skipped": [...], "rows": [{"kind", "where", "evidence", "strength", "build", "hot"}]}`, and run
   `python3 -I "$CC/scripts/rank.py" <that file> <repo>/.kiss/clean/<YYYY-MM-DD>.md`: it numbers the rows in rank
   order and writes the list. When that file exists it stops (exit 2): add `-2`, `-3` and so on to the name. That
   folder must be git-ignored, before the script writes: when `git -C "<repo>" check-ignore -q .kiss/clean/x` fails, add the line
   `.kiss/clean/` to the file that `git -C "<repo>" rev-parse --git-path info/exclude` names (never to a tracked
   file), and say so. Show the saved list as it is, with every column. Done when `git -C "<repo>" status --short`
   equals the status step 1 recorded (less a `?? .kiss/` line that the new exclude line hides).
8. **The owner picks.** Each pick becomes a harness run (kiss-harness, the candidate as its request) or a `/kiss-mini`
   task (kiss-mini); start it only on the owner's word. Done when each pick has its route.
!`python3 -I "${CLAUDE_PLUGIN_ROOT}/rules/feedback.py" 9 kiss-code-clean`

(Agents other than Claude Code: at the end of the run, run `python3 -I <the KISS plugin folder>/rules/feedback.py 9 kiss-code-clean` and follow what it prints.)
