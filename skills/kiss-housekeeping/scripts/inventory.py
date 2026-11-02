#!/usr/bin/env python3
"""Inventory every tracked Markdown file of a repo, for housekeeping. Read-only.

    python3 -I inventory.py <repo> [--old NAME=REGEX ...] > inventory.json
    python3 -I inventory.py --selftest

One row per file: kind (by path, as check_docs.py reads it), lines, last change, title,
inbound links, broken links, old names (from the glossary, or --old), copies, and the
non-Markdown files that name its path (its path users: tests, tools, code, config).
The summary on stderr prints every count with its denominator.
"""
import collections, hashlib, json, os, re, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python3 -I leaves this folder off the path
import check_docs as C  # noqa: E402

TEXT = ("*.py", "*.js", "*.ts", "*.svelte", "*.sh", "*.yml", "*.yaml", "*.toml", "*.json",
        "*.html", "Dockerfile*", "Makefile", "*.cfg", "*.ini")


def main(repo, extra):
    C.use_project_config(repo)
    files = C.tracked(repo)
    every = set(C.tracked(repo, "*"))
    text = {p: open(os.path.join(repo, p), encoding="utf-8", errors="replace").read() for p in files}
    names = C.old_names(repo) + [(n, re.compile(rx), n) for n, rx in extra]
    inbound, broken = collections.Counter(), collections.defaultdict(list)
    for p in files:
        for n, raw, t in C.links(p, text[p]):
            if t is None:
                continue
            if C.exists(t, every):
                if t != p:
                    inbound[t] += 1
            else:
                broken[p].append("%d:%s" % (n, raw))
    code = {}
    for p in C.tracked(repo, *TEXT):
        if not p.startswith(tuple(C.CONFIG["history"])):
            code[p] = open(os.path.join(repo, p), encoding="utf-8", errors="replace").read()
    by_hash = collections.defaultdict(list)
    for p in files:
        by_hash[hashlib.sha1(text[p].encode()).hexdigest()].append(p)
    rows = []
    for p in files:
        body = text[p]
        base = os.path.basename(p)
        distinct = base.lower() not in ("readme.md", "index.md", "notes.md") and len(base) > 8
        users = sorted(q for q, t in code.items() if p in t or (distinct and base in t))
        prose = C.prose(body)
        old = {}                                   # the gate's rule: a line that also gives the current name is fine
        for line in prose.splitlines():
            for name, rx, term in names:
                if rx.search(line) and name not in line:
                    old[term] = old.get(term, 0) + 1
        title = next((l.lstrip("# ").strip() for l in body.splitlines() if l.startswith("#")), "")
        rows.append({
            "path": p, "kind": C.kind(p), "lines": body.count("\n"),
            "date": subprocess.run(["git", "log", "-1", "--format=%cs", "--", p], cwd=repo,
                                   capture_output=True, text=True).stdout.strip(),
            "title": title[:120], "inbound": inbound[p], "broken": broken[p],
            "old": {k: v for k, v in old.items() if v},
            "copy_of": [q for q in by_hash[hashlib.sha1(body.encode()).hexdigest()] if q != p],
            "used_by": users,
        })
    json.dump(rows, sys.stdout, indent=1, ensure_ascii=False)
    n = len(rows)
    kinds = collections.Counter(r["kind"] for r in rows)
    say = lambda label, k, of=n: print("%-34s %d of %d" % (label, k, of), file=sys.stderr)
    print("inventory: %d Markdown files (%s)" % (n, ", ".join("%d %s" % (v, k) for k, v in kinds.items())), file=sys.stderr)
    live = [r for r in rows if r["kind"] in ("living", "log")]
    say("living or log, with no inbound link", sum(1 for r in live if not r["inbound"]), len(live))
    say("files with a broken link", sum(1 for r in rows if r["broken"]))
    say("living or log, with a broken link", sum(1 for r in live if r["broken"]), len(live))
    living = [r for r in rows if r["kind"] in ("living", "agent")]
    say("living or agent, with an old name", sum(1 for r in living if r["old"]), len(living))
    say("files with an exact copy", sum(1 for r in rows if r["copy_of"]))
    say("files a non-Markdown file names", sum(1 for r in rows if r["used_by"]))


def selftest():
    """A scratch repo of 4 pages: 4 rows, the broken link, the tool that names one page's path, and the
    project's own gate CONFIG (its history folder) read from tools/check_docs.py."""
    pages = {"README.md": "# R\n[s](docs/setup-guide.md)\n", "docs/setup-guide.md": "# Setup\n[x](gone.md)\n",
             "docs/notes/2026-10-01-idea.md": "# Idea\n", "tools/build.py": "PAGE = 'docs/setup-guide.md'\n",
             "docs/archive/old.md": "# Old\n", "tools/check_docs.py": "CONFIG = dict(history=['docs/archive/'])\n"}
    with tempfile.TemporaryDirectory() as d:
        for p, body in pages.items():
            os.makedirs(os.path.join(d, os.path.dirname(p)), exist_ok=True)
            open(os.path.join(d, p), "w", encoding="utf-8").write(body)
        subprocess.run(["git", "init", "-q"], cwd=d, check=True)
        out = subprocess.run([sys.executable, "-I", os.path.abspath(__file__), d], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    rows = {r["path"]: r for r in json.loads(out.stdout)}
    assert sorted(rows) == ["README.md", "docs/archive/old.md", "docs/notes/2026-10-01-idea.md", "docs/setup-guide.md"], rows
    assert rows["docs/archive/old.md"]["kind"] == "history", rows["docs/archive/old.md"]
    assert rows["docs/setup-guide.md"]["used_by"] == ["tools/build.py"], rows["docs/setup-guide.md"]
    assert rows["docs/setup-guide.md"]["broken"] == ["2:gone.md"] and rows["docs/setup-guide.md"]["inbound"] == 1
    assert rows["README.md"]["used_by"] == [] and rows["docs/notes/2026-10-01-idea.md"]["kind"] == "record"
    assert "inventory: 4 Markdown files" in out.stderr, out.stderr
    return "inventory selftest ok: 4 rows of 4 pages, 1 path user, 1 broken link, the project's CONFIG"


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(print(selftest()))
    args = sys.argv[1:]
    if not args or args[0].startswith("-"):
        sys.exit(__doc__)
    extra = []
    for i, a in enumerate(args[1:], 1):
        if a == "--old" and i + 1 < len(args):
            extra.append(tuple(args[i + 1].split("=", 1)))
    main(args[0], extra)
