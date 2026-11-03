---
name: kiss-code-clean
description: Give one ranked list of clean-up candidates for a code base - bugs, risky code with no test, slow paths, code to delete, merge or split, shortcut debt and hot spots - each with its evidence and a strength. Reads only; changes no code.
disable-model-invocation: true
allowed-tools: Bash(printenv KISS_FEEDBACK)
---

# KISS code clean

You find what to clean up in a code base and rank it; the owner picks, and each pick is built later by kiss-harness
or kiss-mini-agent. You change no tracked file of the repo: no code, no docs, no `.gitignore`; your one write is the list in the
git-ignored `.kiss/clean/`. `CC` is this skill's folder
(the folder of this file). The scope is the repo, or the folder the owner names.

1. **Check the tools.** In your skill list: `ponytail-audit` and `ponytail-debt` (ponytail), `codebase-design`
   (Matt Pocock's skills); Claude Code and Codex name them `ponytail:<name>` and `mattpocock-skills:<name>`. Each one
   in the list is loaded in its step: reading the code yourself instead is no substitute. On the shell: `codegraph status "<repo>"` prints `Project: <repo>` (the repo is indexed),
   and `$CC/../kiss-harness/scripts/cgcallers.py`. Note each one that is missing; step 7 names the part it skipped.
   Done when each tool is found or noted.
2. **Hot spots.** `git -C "<repo>" log --since="6 months ago" --name-only --format=` and count the changes per file:
   the top ten are the hot spots. A candidate in a hot spot ranks higher (a clean-up there pays off soonest). No
   history: say so. Done when the list is written down.
3. **Audit.** Load `ponytail-audit` on the scope: its ranked report (bugs, security, load, risky code with no test,
   slow paths, what to delete, merge or split) gives the first candidates, each with its file, line and reason.
   Without it, read the entry points and the hot spots yourself for the same kinds. Done when each finding has its
   file and line.
4. **Debt.** Load `ponytail-debt` on the scope: each `shortcut:` comment is a candidate with its limit. Without it,
   `git -C "<repo>" grep -n "shortcut:"`. Done when every `shortcut:` line is listed.
5. **Architecture.** Look for deepening by the rules in [references/architecture.md](references/architecture.md),
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
7. **One ranked list.** Join every candidate into one list, ranked: bugs and security first, then risky code with
   no test, load and slow paths, delete / merge / split, then `shortcut:` debt; inside a rank, `Strong` before
   `Speculative` and a hot spot first. Each row: number, kind, `file:line`, the evidence (the check that found it
   and its result), the strength, and the build it needs (a harness run for a change across modules or an
   interface, a `/mini` task for a small local one). Start the list with one line per skipped part ("ponytail not
   installed: no audit report, no debt ledger"). Save it as `<repo>/.kiss/clean/<YYYY-MM-DD>.md`; that folder must
   be git-ignored: when `git -C "<repo>" check-ignore -q .kiss/clean/x` fails, add `.kiss/` to
   `<repo>/.git/info/exclude` (never to a tracked file) and say so. Show the list. Done when `git -C "<repo>"
   status --short` shows no change to a tracked file.
8. **The owner picks.** Each pick becomes a harness run (kiss-harness, the candidate as its request) or a `/mini`
   task (kiss-mini-agent); start it only on the owner's word. Done when each pick has its route.
9. **KISS feedback**, in every run, also one that stops early or fails: after your last work call, run `printenv KISS_FEEDBACK` as its own tool call, with nothing before or after it in that call. When it prints `1`, read [`rules/feedback.md`](../../rules/feedback.md) and `version` in `gemini-extension.json` at the plugin root, then end your final message with the block (no path outside the KISS repo, none that starts with `/`, `~` or a drive letter). When it prints anything else, or the call is refused or fails, end your final message with your report alone, with no line about this step.
