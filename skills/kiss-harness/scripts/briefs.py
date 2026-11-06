#!/usr/bin/env python3
"""Write one brief and one seed file per ticket.

  python3 -I briefs.py RUN W BRANCH ID [ID ...]
  python3 -I briefs.py --selftest

The brief (RUN/briefs/task-<ID>-brief.md) holds W, the read-first line, the ticket and one line that points to the
seed. The seed (RUN/briefs/seed-<ID>.md) is CodeGraph output, read after a sync: for each symbol of the ticket that
exists (a bare name, `Class.method` or `Class::method`), `codegraph node` and `codegraph callers --limit 100` (or
`codegraph explore` of it when its node holds no code), then the ticket's `seeds` queries through `explore`. A
ticket whose files CodeGraph does not index gets "No code seed". The rules live in the implementer prompt.
"""
import json, os, subprocess, sys, tempfile

CALLERS_LIMIT = 100   # rules/codegraph.md, "Subagents" item 3
NO_CODE = "No code seed: this ticket edits files CodeGraph does not index."


def exts(paths):
    """The file types ('.py') in a list of paths; a name with no dot after its folder has none."""
    return {os.path.splitext(p.strip())[1] for p in paths} - {""}


def run(*a, timeout=120):
    return subprocess.run(a, capture_output=True, text=True, timeout=timeout)


def file_types(W, run=run):
    """(indexed, not indexed) file types in W, read from CodeGraph and git, never written by hand."""
    indexed = exts(run("codegraph", "files", "-p", W, "--format", "flat", "--no-metadata").stdout.splitlines())
    assert indexed, f"codegraph files lists nothing for {W}"
    return sorted(indexed), sorted(exts(run("git", "-C", W, "ls-files").stdout.splitlines()) - indexed)


def exists(W, name, run=run):
    """True when the index holds a symbol with exactly this name (a ticket may name one it creates). A `Class.method`
    or `Class::method` name matches a node whose qualified name is `Class::method` or ends with `::Class::method`."""
    out = run("codegraph", "query", "-p", W, "-j", "-l", "50", name).stdout
    q = name.replace(".", "::")
    try:
        return any(h["node"]["name"] == name or "::" in q and (h["node"].get("qualifiedName") == q
                   or str(h["node"].get("qualifiedName")).endswith("::" + q)) for h in json.loads(out or "[]"))
    except (ValueError, KeyError, TypeError, AttributeError):
        return False


def empty(out):
    """No result: judged on the head only, since a result's source code may hold these words."""
    head = "\n".join(out.strip().splitlines()[:6])
    return not head or "No results found" in head or "Found 0 symbols" in head


def sync(W, run=run):
    """Sync the worktree index so the seed reads today's code; a timeout is reported, not fatal."""
    try:
        r = run("codegraph", "sync", "-q", W, timeout=900)
        return "" if r.returncode == 0 else f"`codegraph sync` failed ({r.returncode}): the seed may be stale."
    except subprocess.TimeoutExpired:
        return "`codegraph sync` ran over 900 s: the seed may be stale; run the sync yourself first."


def seed(W, t, indexed, run=run):
    """The seed text: node and callers of each existing symbol (explore of one whose node holds no code), then explore
    on each query."""
    files = t.get("files") or []
    if files and not exts(files) & set(indexed):
        return NO_CODE
    parts = []
    for name in t.get("symbols") or []:
        if not exists(W, name, run):
            continue
        node = run("codegraph", "node", "-p", W, name).stdout
        if "```" not in node:                                 # a type whose node is only a member list (D19)
            parts.append(f'### `codegraph explore -p "{W}" "{name}"` (its node holds no code)\n{run("codegraph", "explore", "-p", W, name).stdout}')
            continue
        parts.append(f'### `codegraph node -p "{W}" {name}`\n{node}')
        args = ["callers", "-p", W, "--limit", str(CALLERS_LIMIT), name]
        parts.append(f"### `codegraph {' '.join(args[:2])} \"{W}\" {' '.join(args[3:])}`\n{run('codegraph', *args).stdout}")
    queries = t.get("seeds") or []
    # Several queries share one query's size of seed: fewer files each (D10); one keeps CodeGraph's default.
    size = ["--max-files", str(max(3, 12 // len(queries)))] if len(queries) > 1 else []
    for q in queries:
        out = run("codegraph", "explore", "-p", W, *size, q).stdout
        if not empty(out):
            parts.append(f'### `codegraph explore -p "{W}" "{q}"`\n{out}')
    if not parts and files:
        q = " ".join(files[:6])
        out = run("codegraph", "explore", "-p", W, q).stdout
        parts.append(f'### `codegraph explore -p "{W}" "{q}"` (the ticket\'s files: it names no symbol and its queries found nothing)\n{out}')
    return "\n".join(parts) or "(empty: the ticket names no existing symbol or file; start from `codegraph explore` yourself)"


def main(R, W, branch, ids, run=run):
    tickets = {t["id"]: t for t in json.load(open(os.path.join(R, "tickets.json")))}
    status = run("codegraph", "status", W).stdout
    assert f"Project: {W}" in status, f"wrong or missing index for {W}:\n{status}"
    stale = sync(W, run)
    indexed, unindexed = file_types(W, run)
    os.makedirs(os.path.join(R, "briefs"), exist_ok=True)
    for i in ids:
        t = tickets[i]
        issue = open(os.path.join(R, "issues", f"{i}.md")).read()
        seed_path = os.path.join(R, "briefs", f"seed-{i}.md")
        text = f"""# Seed — ticket {i}

{stale or "The index was synced just before this seed."} In W, CodeGraph indexes {', '.join(indexed)}; it does not
index {', '.join(unindexed) or 'any other tracked type'}, nor git-ignored files. The output below is verbatim CodeGraph
output: treat it as already read.

{seed(W, t, indexed, run)}
"""
        brief = f"""# Brief — ticket {i}: {t['title']}

Worktree W = `{W}`, branch `{branch}` (already checked out).

Read first: `{R}/spec.md`, `{R}/decisions.md` and `{R}/progress.md` (once, at the start), then this brief.

## The ticket (`{R}/issues/{i}.md`)
{issue}
Read `{seed_path}` now.
"""
        for path, body in ((seed_path, text), (os.path.join(R, "briefs", f"task-{i}-brief.md"), brief)):
            with open(path, "w") as f:
                f.write(body)
            print(i, len(body), "chars", path)


def selftest():
    assert exts(["web/a.svelte", " core/b.py", "Makefile", "x/.env", "Files (291):"]) == {".svelte", ".py"}
    assert empty("ℹ No results found for \"x\"") and not empty("**Exploration: x**\nFound 3 symbols")
    W = "/w/my app"
    def index(*nodes, code=0, out=None):                     # `codegraph query` prints these nodes, whatever the name
        return lambda *a, timeout=120: subprocess.CompletedProcess(a, code, out if out is not None else json.dumps([{"node": n} for n in nodes]), "")
    lsp = {"name": "read", "qualifiedName": "Lsp::read"}
    assert exists(W, "Lsp.read", index(lsp)) and exists(W, "Lsp::read", index(lsp)) and exists(W, "read", index(lsp))
    assert exists(W, "Lsp.read", index({"name": "read", "qualifiedName": "app::Lsp::read"}))
    for other in ("Other::read", "MyLsp::read", "Lsp::read2", "read"):
        assert not exists(W, "Lsp.read", index({"name": "read", "qualifiedName": other})), other
    assert not exists(W, "rea", index(lsp)) and not exists(W, "Lsp", index(lsp)) and exists(W, "a.py", index({"name": "a.py", "qualifiedName": "x/a.py"}))
    for code, out in ((1, ""), (1, "error: no index"), (0, "not json"), (0, '[{"x": 1}]'), (0, '{"node": 1}')):
        assert not exists(W, "Lsp.read", index(code=code, out=out)), (code, out)   # a failed lookup: no match, no crash
    known = [{"name": "foo", "qualifiedName": "foo"}, lsp, {"name": "Shape", "qualifiedName": "Shape"}]

    def fake(*a, timeout=120):
        cmd = a[-1] if a[0] == "git" else a[1]
        out = {"status": f"Project: {W}\n", "sync": "",
               "files": "Files (1):\n\n  skills/x/a.py\n", "ls-files": "skills/x/a.py\nREADME.md\n",
               "query": json.dumps([{"node": n} for n in known]),
               "node": f"**{a[-1]}** (struct)\n**Members (2):**\n" if a[-1] == "Shape" else f"NODE-OF {a[-1]}\n```py\ncode\n```\n",
               "callers": f"CALLERS-OF {a[-1]}\n",
               "explore": f"**Exploration: {a[-1]}**\nFound 2 symbols\n" + "code\n" * 9 + "    if 'No results found' in out:\n"}[cmd]
        return subprocess.CompletedProcess(a, 0, out, "")

    with tempfile.TemporaryDirectory() as R:
        rows = [{"id": "T-1", "title": "code", "files": ["skills/x/a.py"], "symbols": ["foo", "new_one", "Lsp.read", "Lsp::read", "Shape"], "seeds": ["foo bar"]},
                {"id": "T-2", "title": "docs", "files": ["README.md"]}]
        json.dump(rows, open(os.path.join(R, "tickets.json"), "w"))
        os.makedirs(os.path.join(R, "issues"))
        for r in rows:
            open(os.path.join(R, "issues", r["id"] + ".md"), "w").write(f"# {r['id']}: {r['title']}\n")
        main(R, W, "br", ["T-1", "T-2"], run=fake)
        read = lambda n: open(os.path.join(R, "briefs", n)).read()
        s1, s2, b1 = read("seed-T-1.md"), read("seed-T-2.md"), read("task-T-1-brief.md")
        for want in ("NODE-OF foo", "CALLERS-OF foo", "Exploration: foo bar", "NODE-OF Lsp.read", "CALLERS-OF Lsp.read",
                     "NODE-OF Lsp::read", "CALLERS-OF Lsp::read", f'### `codegraph explore -p "{W}" "Shape"`', "Exploration: Shape"):
            assert want in s1, (want, s1)
        assert "(struct)" not in s1 and "CALLERS-OF Shape" not in s1, s1   # a node with no code: explore it, not node and callers
        assert "new_one" not in s1, s1                         # a symbol the ticket creates has no seed yet
        assert s1.index("NODE-OF foo") < s1.index("CALLERS-OF foo") < s1.index("Exploration: foo bar"), s1
        assert NO_CODE in s2 and "NODE-OF" not in s2, s2
        assert [l for l in b1.splitlines() if "seed-T-1.md" in l] == [f"Read `{R}/briefs/seed-T-1.md` now."], b1
        for rule in ("codegraph", "cgcallers", "Commit", "Tests during the work", "sync"):
            assert rule not in b1, (rule, b1)                 # the rules live in the implementer prompt only
    calls = []
    def counting(*a, timeout=120):
        calls.append(a)
        return fake(*a, timeout=timeout)
    for n, flag in ((2, ["--max-files", "6"]), (3, ["--max-files", "4"]), (5, ["--max-files", "3"]), (1, [])):
        calls.clear()                                         # n queries share one query's size: max(3, 12 // n) files each
        seed(W, {"seeds": ["q%d" % i for i in range(n)]}, [".py"], counting)
        got = [list(a[4:-1]) for a in calls if a[1] == "explore"]
        assert got == [flag] * n, (n, got)
    print("briefs selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        selftest()
    else:
        main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:])
