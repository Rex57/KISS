## CodeGraph — the rule

**Installer trap:** `codegraph install` adds a `CODEGRAPH_START`/`CODEGRAPH_END` block to your instructions file: delete it;
this rule holds its content.

**Which index.** Decide once per checkout, before the first query. `W` = `git rev-parse --show-toplevel` in the folder
of the files you read or edit. `W/.codegraph/` exists → use it. Else, when `W` is a git worktree whose main checkout
has an index → run `codegraph init "W" </dev/null` now. Else skip CodeGraph: indexing is the user's decision.
`codegraph status "W"` must print `Project: W`; any other path is another branch's index.

**Every call names `W`:** CLI `-p "W"`; `status`, `sync` and `init` take `"W"` as their argument; MCP
`projectPath: "W"`. Never rely on the shell's folder or the MCP server's default project. A result "from a different
git worktree (<path>)" is W's when that path is W; any other path is the wrong index.

**Keep it fresh:** a worktree runs no watcher: after each batch of edits run `codegraph sync -q "W"` (give it a long
timeout after a large change).

**CodeGraph first, for every code question and before every edit:** an area or a question →
`codegraph explore -p "W" "<names or question>"`; one function → `codegraph node -p "W" <name>` (a method as
`Class.method`), never `grep "def X"` + `sed -n`; the tests for changed files → `codegraph affected -p "W" <files>`.

**grep, find or Read only for:** a literal, a count, or a file CodeGraph does not index
(`codegraph files -p "W" --format flat --no-metadata` lists what it does).

**`callers` is incomplete:** it misses a method called on an untyped parameter or value, and a call through `getattr`
or an index with a string. 0 callers proves nothing: with 0 callers or two or more definitions, and before a delete,
rename or signature change, run `cgcallers NAME -p "W"` and read every `[grep only]` and `[lsp]` line. Ask `explore`
with names, not a sentence.

**Subagents** ignore a "use CodeGraph" line. In every brief: (1) give `W`, indexed and status-checked, and the exact
commands with `-p "W"`; (2) make CodeGraph step 1, with `codegraph sync -q "W"` after its edits; (3) seed it: run
`codegraph sync -q "W"`, then paste `codegraph explore -p "W"` on the symbols it changes and reads; (4) before you accept its work, check its changes by
script: `cgcallers` on each name it deleted, renamed or re-signed (in a KISS run, `callcheck.py` on its commits).
