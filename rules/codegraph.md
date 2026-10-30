## CodeGraph — the rule

**Installer trap:** `codegraph install` adds a `CODEGRAPH_START`/`CODEGRAPH_END` block to this file. Delete that
block: this section, outside the markers, already holds its content.

**Which index.** Decide once per checkout, before the first query. Many checkouts can each hold an index; the right
one is always the one at the root of the files you read or edit.

1. `W` = `git rev-parse --show-toplevel`, run in the folder of those files. `W/.codegraph/` exists → use it.
2. Else, if `W` is a git worktree whose main checkout (the parent of
   `git rev-parse --path-format=absolute --git-common-dir`) has an index → run `codegraph init -y "W"` now, without
   asking: the owner already chose to index this repo.
3. Else → skip CodeGraph entirely; indexing is the user's decision.
4. `codegraph status "W"` must print `Project: W`. Any other path (`Index from:` the main checkout) is the wrong
   index, from another branch, and CodeGraph may give no warning: go back to step 2.

**Every call names `W`:** CLI `-p "W"` on `explore`, `node`, `query`, `callers`, `callees`, `impact`, `affected`,
`files`, `context`; `status`, `sync` and `init` take `"W"` as their argument; MCP `projectPath: "W"`. Never rely on
the shell's working folder (it resets) or the MCP server's default project (the main checkout). Source that a
CodeGraph prompt hook injects comes from the main checkout's index: in a worktree, query again with `-p "W"` before
you edit from it.

**Keep it fresh:** the main checkout runs a watcher (~1 s behind); a worktree runs none: after each batch of edits
run `codegraph sync -q "W"`, or new symbols and callers are missing (after a large build one sync can take minutes:
allow a long timeout). `git worktree remove` deletes the worktree's index; the main index skips worktree folders
that `.gitignore` lists, so it stays clean.

**CodeGraph first, for every code question and before every edit:** MCP `codegraph_explore`, or the shell
`codegraph …`, which always works and prints the same output.

| Need | Call |
|---|---|
| How/where is X, an area, several names at once | `codegraph explore "<question or names>"`: verbatim line-numbered source + call paths (also dynamic-dispatch hops grep cannot follow); safe to edit from |
| One symbol or file in full | `codegraph node <name>`: ONE name per call (two is an error); a method by its qualified name (`Engine.ack`): a bare common name prints every definition |
| Who depends on it | `codegraph callers` / `callees` / `impact <symbol>`; "Showing 20 of N" (callers, callees) is a cut list: run it again with `--limit N` (`impact` has no `--limit`). Before a delete, rename, signature change or caller count: `cgcallers` (below) |
| Tests covering changed files | `codegraph affected <files…>` |
| Find a symbol by name | `codegraph query "<name>"` |
| Which index, is it current | `codegraph status "W"`; `codegraph sync "W"` |

**Two outputs mislead.** (1) A long tool result that shows a preview and names a file with the full output: read
that file before you act. (2) Run from another checkout of the same repo, `-p "W"` prints "CodeGraph results below
come from a different git worktree (<path>)" with `init -i` advice: when that path is W, the results are W's
(ignore the advice); any other path is the wrong index (step 4).

**grep, find or Read only for:** a literal (route, env name, error text), a count, or a file CodeGraph does not
index (configs, docs, logs, JS inside `.html`). Before you call a file type unindexed, or say so in a brief, check:
`codegraph files -p "W" --format flat --no-metadata`. Never `grep "def X"` + `sed -n` to read a function: that is
`codegraph node X`. If CodeGraph's answer is incomplete, say so, then fall back to `cgcallers`, a word grep of the
name, or a file read.

**`callers` is incomplete:** it misses a call after `import X` inside a function, a call to a function named `get`
or `copy`, a function passed as a value (route tables, callbacks), `getattr` with a string, a local alias and
recursion. **Before you delete, rename or change a signature, or give a caller count:** run
`cgcallers NAME -p "W"` (CodeGraph plus a word grep; each caller marked `[both]`, `[grep only]` or `[cg only]`) and
read every `[grep only]` line. Delete only when it shows no caller, route, test, string or doc use.

**Subagents** ignore a "use CodeGraph" line. In every brief, mergers and checkers included:

1. **Give `W`:** the absolute checkout path, already indexed and `status`-checked, and the exact commands with
   `-p "W"` / `projectPath`. The agent never runs `init` and never queries another path, except an agent in a
   worktree it makes itself: it runs "Which index" as its STEP 0, `init` included.
2. **STEP 1 is CodeGraph,** with the grep limits, the `callers` gaps and the two misleading outputs above, and
   `codegraph sync -q "W"` after its edits.
3. **Seed the brief:** run `codegraph sync -q "W"` yourself, then `codegraph explore -p "W"` on the task's existing
   symbols (the ones it changes and the ones it reads), plus `codegraph callers -p "W"` of each one it changes
   (widen a cut list), and paste the output in, so the agent starts from it, not from grep. Leave out names the task
   only creates: `explore` returns unrelated word matches for them.
4. **Check the work:** the report lists its CodeGraph queries and one reason per grep; count the calls in its
   transcript before you accept it (a listed call is not always a made call).
