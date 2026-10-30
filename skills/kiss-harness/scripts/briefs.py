#!/usr/bin/env python3
"""Write one brief per ticket, seeded with `codegraph explore -p W` and the callers of what it edits.

  python3 -I briefs.py RUN W BRANCH ID [ID ...]

RUN holds tickets.json and issues/ (tickets.py render). The index is synced before the seed; the seed reads only
symbols that exist, plus `codegraph callers` of each one the ticket edits; an empty seed falls back to the
ticket's files.
"""
import json, os, subprocess, sys

CALLERS_LIMIT = 40
HB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def exts(paths):
    """The file types ('.py') in a list of paths; a name with no dot after its folder has none."""
    return {os.path.splitext(p.strip())[1] for p in paths} - {""}


def run(*a, timeout=120):
    return subprocess.run(a, capture_output=True, text=True, timeout=timeout)


def file_types(W):
    """(indexed, not indexed) file types in W, read from CodeGraph and git, never written by hand."""
    indexed = exts(run("codegraph", "files", "-p", W, "--format", "flat", "--no-metadata").stdout.splitlines())
    assert indexed, f"codegraph files lists nothing for {W}"
    return sorted(indexed), sorted(exts(run("git", "-C", W, "ls-files").stdout.splitlines()) - indexed)


def exists(W, name):
    """True when the index holds a symbol with exactly this name (a ticket may name one it creates)."""
    out = run("codegraph", "query", "-p", W, "-j", "-l", "50", name).stdout
    try:
        return any(h["node"]["name"] == name for h in json.loads(out or "[]"))
    except (ValueError, KeyError, TypeError):
        return False


def empty(out):
    return not out.strip() or "No results found" in out or "Found 0 symbols" in out


def sync(W):
    """Sync the worktree index so the seed reads today's code; a timeout is reported, not fatal."""
    try:
        r = run("codegraph", "sync", "-q", W, timeout=900)
        return "" if r.returncode == 0 else f"`codegraph sync` failed ({r.returncode}): the seed may be stale."
    except subprocess.TimeoutExpired:
        return "`codegraph sync` ran over 900 s: the seed may be stale; run the sync yourself first."


def seed(W, t):
    """The SEED text: explore on each query, then callers of each existing symbol the ticket edits."""
    parts = []
    # a ticket may carry no seeds: its symbols are then the one query
    for q in t.get("seeds") or ([" ".join(t["symbols"])] if t.get("symbols") else []):
        out = run("codegraph", "explore", "-p", W, q).stdout
        if not empty(out):
            parts.append(f'### `codegraph explore -p "{W}" "{q}"`\n{out}')
    if not parts and t.get("files"):
        q = " ".join(t["files"][:6])
        out = run("codegraph", "explore", "-p", W, q).stdout
        parts.append(f'### `codegraph explore -p "{W}" "{q}"` (the ticket\'s files: its queries found nothing)\n{out}')
    for name in t.get("symbols") or []:
        if exists(W, name):
            out = run("codegraph", "callers", "-p", W, "--limit", str(CALLERS_LIMIT), name).stdout
            parts.append(f'### `codegraph callers -p "{W}" --limit {CALLERS_LIMIT} {name}`\n{out}')
    return "\n".join(parts) or "(empty: the ticket names no existing symbol or file; start from `codegraph explore` yourself)"


def main(R, W, branch, ids):
    tickets = {t["id"]: t for t in json.load(open(os.path.join(R, "tickets.json")))}
    status = run("codegraph", "status", W).stdout
    assert f"Project: {W}" in status, f"wrong or missing index for {W}:\n{status}"
    stale = sync(W)
    indexed, unindexed = file_types(W)
    P = f'-p "{W}"'
    for i in ids:
        t = tickets[i]
        issue = open(os.path.join(R, "issues", f"{i}.md")).read()
        brief = f"""# Brief — ticket {i}: {t['title']}

Worktree W = `{W}`, branch `{branch}` (already checked out; never switch or create branches). W is
indexed: `codegraph status "{W}"` prints `Project: {W}`. Every CodeGraph call names W (`{P}`; MCP
`projectPath: "{W}"`). Never run `codegraph init`. {stale or "The index was synced just before this brief."}

Read first: `{R}/spec.md`, `{R}/decisions.md` and `{R}/progress.md` (once, at the start), then this brief.

## The CodeGraph rule (binding)
STEP 1 is CodeGraph: start from the SEED below (verbatim CodeGraph output: treat it as already read). Then:
- `codegraph node {P} <name>` for each symbol you change, and for EVERY function your new code, tests or docs
  name (a docs line that states what a function does is a code fact: check it).
- `codegraph callers {P} <name>` for each shared function you edit; check every caller.
- Before a delete, rename or signature change: `python3 -I "{HB}/scripts/cgcallers.py" <name> {P}`; read
  every `[grep only]` line.
Usage notes:
1. `codegraph node` takes ONE name per call; for several names use `codegraph explore {P} "a b c"`.
2. Use a qualified name for a method (`Engine.ack`); a bare common name prints every definition.
3. A caller list that ends "+N more" is cut: run `codegraph callers {P} --limit 100 <name>`.
4. The line "results come from a different git worktree" is expected when you pass `{P}` from another folder:
   the results are W's. A tool result that shows a preview and names a file: read that file.
grep/find/Read only for a literal (a route, an env name, a payload key, error text, SQL), a file CodeGraph does
not index, or a count. In W, CodeGraph indexes {', '.join(indexed)}; it does not index {', '.join(unindexed)},
nor git-ignored files such as `.kiss/` (from `codegraph files {P} --format flat --no-metadata` and
`git ls-files` when this brief was written). Never `grep -n "def X"` + `sed -n` (that is `codegraph node`).
After each batch of edits and before you return: `codegraph sync -q "{W}"` (give it a 10-minute timeout;
Claude Code: the Bash tool's `timeout: 600000`).

## The ticket (`{R}/issues/{i}.md`)
{issue}
## Tests during the work
Your own tests, the tests `codegraph affected {P} <changed files>` names, and the selftest of each changed
module that has one, run as the project facts file says. Never the full check: the controller runs it once at
the end.

## Commit
One commit, explicit `git add` / `git rm` paths, message `{t['title']}` (you may shorten it), with the trailer
lines the project's instructions name.

## SEED (run by the dispatcher)
{seed(W, t)}
"""
        path = os.path.join(R, "briefs", f"task-{i}-brief.md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").write(brief)
        print(i, len(brief), "chars", path)


if __name__ == "__main__":
    assert exts(["web/a.svelte", " core/b.py", "Makefile", "x/.env", "Files (291):"]) == {".svelte", ".py"}
    assert empty("ℹ No results found for \"x\"") and not empty("**Exploration: x**\nFound 3 symbols")
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:])
