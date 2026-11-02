#!/usr/bin/env python3
"""Move Markdown pages and keep every pointer to them working. Dry run unless --apply.

    python3 -I move_docs.py <repo> <moves.tsv> [--apply]
    python3 -I move_docs.py --selftest

moves.tsv: one `old<TAB>new` per line (repo-relative; # starts a comment). A line whose old
path is a folder moves every tracked file under it. With --apply it:
  1. git mv each file (folders made as needed);
  2. rewrites each relative Markdown link that the move breaks, in every tracked .md file,
     from the moved file and to it (anchors kept; untouched links keep their spelling), and
     a label that showed the old name, [`old.md`](...), gets the new repo path;
  3. replaces each old repo-relative path (one with a /) where it stands as a word, in every
     tracked text file outside history: code comments, tests, tools, config, prose;
  4. prints each place that still names an old file by its bare name: a path user to fix by
     hand in the same commit (an os.path.join, a loop over names, a relative mention).
A root file (no / in its path) is never replaced as text: `git show <tag>:FILE` must keep it.
"""
import os, re, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python3 -I leaves this folder off the path
import check_docs as C  # noqa: E402
from inventory import TEXT  # noqa: E402


def plan(repo, tsv):
    files = set(C.tracked(repo, "*"))
    moves = {}
    for line in open(tsv, encoding="utf-8"):
        line = line.split("#", 1)[0].rstrip("\n")
        if not line.strip():
            continue
        old, new = [x.strip().rstrip("/") for x in line.split("\t")]
        under = sorted(f for f in files if f.startswith(old + "/"))
        if old in files:
            moves[old] = new
        elif under:
            moves.update({f: new + f[len(old):] for f in under})
        else:
            sys.exit("not tracked: %s" % old)
    taken = [n for n in moves.values() if os.path.exists(os.path.join(repo, n))]
    if taken:
        sys.exit("already exists: %s" % taken)
    return moves


def where(path, moves, files):
    """The new home of a path; of a folder only when every tracked file in it moved to one new folder."""
    if path in moves:
        return moves[path]
    inside = [f for f in files if f.startswith(path + "/")] if path else []
    if inside and all(f in moves for f in inside):
        heads = {moves[f][: len(moves[f]) - len(f) + len(path)] for f in inside}
        if len(heads) == 1:                             # the folder moved as a whole, its tree intact
            return heads.pop()
    return path


def relink(old_path, new_path, text, moves, files):
    def fix(m):
        raw = m.group(1)
        if re.match(r"^[a-zA-Z][\w+.-]*:", raw) or raw.startswith(("#", "/")):
            return m.group(0)
        target, sep, anchor = raw.partition("#")
        resolved = os.path.normpath(os.path.join(os.path.dirname(old_path), target))
        dest = where(resolved, moves, files)
        if dest == resolved and new_path == old_path:
            return m.group(0)
        rel = os.path.relpath(dest, os.path.dirname(new_path) or ".")
        if target.endswith("/") and not rel.endswith("/"):
            rel += "/"
        return m.group(0).replace(raw, rel + sep + anchor, 1)
    out, pos = [], 0
    for f in C.FENCE.finditer(text):                   # a link inside a code sample stays as written
        out.append(C.LINK.sub(fix, text[pos:f.start()]))
        out.append(f.group(0))
        pos = f.end()
    out.append(C.LINK.sub(fix, text[pos:]))
    return "".join(out)


LABEL = re.compile(r"\[`([^`]+)`\]\(\s*([^)\s#]+)(#[^)]*)?\)")


def relabel(new_path, text, moves):
    """A link labelled with its target's old name gets the new path: [`old.md`](new/path.md)."""
    back = {n: o for o, n in moves.items()}
    def fix(m):
        label, target = m.group(1), m.group(2)
        if re.match(r"^[a-zA-Z][\w+.-]*:", target):
            return m.group(0)
        dest = os.path.normpath(os.path.join(os.path.dirname(new_path), target))
        old = back.get(dest)
        relative = old and os.path.normpath(os.path.join(os.path.dirname(new_path), label)) == old
        if not old or label == dest or not (relative or old == label or old.endswith("/" + label)):
            return m.group(0)
        # a label written as a relative path (`../docs/x.md`) keeps that style
        return m.group(0).replace("`%s`" % label, "`%s`" % (target if relative else dest), 1)
    return LABEL.sub(fix, text)


def repath(text, moves):
    for old in sorted((o for o in moves if "/" in o), key=len, reverse=True):
        text = re.sub(r"(?<![\w./:-])" + re.escape(old) + r"(?![\w/-])", moves[old], text)
    return text


def main(repo, tsv, apply):
    C.use_project_config(repo)
    moves = plan(repo, tsv)
    md = C.tracked(repo)
    files = set(C.tracked(repo, "*"))
    texts = {p: open(os.path.join(repo, p), encoding="utf-8").read() for p in md}
    for old, new in sorted(moves.items()):
        print("%s %s -> %s" % ("mv" if apply else "would mv", old, new))
    if not apply:
        print("dry run: %d moves; --apply to make them" % len(moves))
        return
    for old, new in moves.items():
        os.makedirs(os.path.join(repo, os.path.dirname(new)) or repo, exist_ok=True)
        subprocess.run(["git", "mv", old, new], cwd=repo, check=True)
    changed = 0
    for old_path, text in texts.items():
        new_path = moves.get(old_path, old_path)
        out = relabel(new_path, relink(old_path, new_path, text, moves, files), moves)
        if not new_path.startswith(tuple(C.CONFIG["history"])):
            out = repath(out, moves)
        if out != text:
            open(os.path.join(repo, new_path), "w", encoding="utf-8").write(out)
            changed += 1
    for p in C.tracked(repo, *TEXT):
        if p.endswith(".md") or p.startswith(tuple(C.CONFIG["history"])):
            continue
        t = open(os.path.join(repo, p), encoding="utf-8", errors="replace").read()
        out = repath(t, moves)
        if out != t:
            open(os.path.join(repo, p), "w", encoding="utf-8").write(out)
            changed += 1
            print("repathed %s" % p)
    print("%d moves, %d files rewritten" % (len(moves), changed))
    left = []
    for p in C.tracked(repo, *TEXT, "*.md"):
        if p.endswith(".md") and C.kind(p) in ("record", "history"):
            continue                                       # a record keeps its words; its links are already fixed
        if p.startswith(tuple(C.CONFIG["history"])):
            continue
        t = open(os.path.join(repo, p), encoding="utf-8", errors="replace").read()
        for n, line in enumerate(t.splitlines(), 1):
            for old, new in moves.items():
                base = os.path.basename(old)
                if base not in line or base.lower() in ("readme.md", "index.md"):
                    continue
                if base != os.path.basename(new) or (not p.endswith(".md") and new not in line):
                    left.append("%s:%d names %s (now %s)" % (p, n, base, new))   # renamed, or code (os.path.join)
                    continue
                for frag in re.findall(r"(?<![\w.-])((?:[\w.-]+/)+)" + re.escape(base), line):
                    whole = frag + base                    # a partial path that still names the old folder
                    if old.endswith(whole) and not new.endswith(whole):
                        left.append("%s:%d names %s (now %s)" % (p, n, whole, new))
    if left:
        print("path users to check by hand (%d):" % len(set(left)))
        print("\n".join("  " + x for x in sorted(set(left))))


def selftest():
    """A scratch repo: a dry run changes no byte and no git state; --apply moves the page and fixes
    its links (anchor kept), the label that named it, and the full path in a tool; a page in the
    project's own history folder (its tools/check_docs.py CONFIG) keeps its words."""
    pages = {"README.md": "# R\n[guide](docs/old/setup.md#install)\n[`docs/old/setup.md`](docs/old/setup.md)\n",
             "docs/old/setup.md": "# Setup\n## Install\n[back](../../README.md)\n",
             "tools/build.py": "PAGE = 'docs/old/setup.md'\n",
             "docs/archive/old.md": "# Old\nThe guide was docs/old/setup.md.\n",
             "tools/check_docs.py": "CONFIG = dict(history=['docs/archive/'])\n"}
    def tree(d):
        out = {}
        for root, dirs, names in os.walk(d):
            dirs[:] = [x for x in dirs if x != ".git"]
            for n in names:
                p = os.path.join(root, n)
                out[os.path.relpath(p, d)] = open(p, "rb").read()
        status = subprocess.run(["git", "status", "--porcelain"], cwd=d, capture_output=True, text=True).stdout
        return out, status
    with tempfile.TemporaryDirectory() as d:
        repo = os.path.join(d, "repo")
        for p, body in pages.items():
            os.makedirs(os.path.join(repo, os.path.dirname(p)), exist_ok=True)
            open(os.path.join(repo, p), "w", encoding="utf-8").write(body)
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]
        subprocess.run(git[:1] + ["init", "-q"], cwd=repo, check=True)
        subprocess.run(git + ["add", "-A"], cwd=repo, check=True)
        subprocess.run(git + ["commit", "-qm", "pages"], cwd=repo, check=True)
        tsv = os.path.join(d, "moves.tsv")
        open(tsv, "w").write("docs/old/setup.md\tdocs/setup.md\n")
        me = [sys.executable, "-I", os.path.abspath(__file__), repo, tsv]
        before = tree(repo)
        out = subprocess.run(me, capture_output=True, text=True)
        assert out.returncode == 0 and "dry run: 1 moves" in out.stdout, (out.stdout, out.stderr)
        assert tree(repo) == before, "the dry run changed the tree"
        out = subprocess.run(me + ["--apply"], capture_output=True, text=True)
        assert out.returncode == 0, out.stderr
        got = {p: b.decode() for p, b in tree(repo)[0].items()}
    assert got == {"README.md": "# R\n[guide](docs/setup.md#install)\n[`docs/setup.md`](docs/setup.md)\n",
                   "docs/setup.md": "# Setup\n## Install\n[back](../README.md)\n",
                   "tools/build.py": "PAGE = 'docs/setup.md'\n",
                   "docs/archive/old.md": "# Old\nThe guide was docs/old/setup.md.\n",
                   "tools/check_docs.py": "CONFIG = dict(history=['docs/archive/'])\n"}, got
    return "move_docs selftest ok: a dry run changes nothing; --apply fixes links, anchors, labels and paths; history keeps its words"


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(print(selftest()))
    a = [x for x in sys.argv[1:] if x != "--apply"]
    if len(a) != 2:
        sys.exit(__doc__)
    main(a[0], a[1], "--apply" in sys.argv)
