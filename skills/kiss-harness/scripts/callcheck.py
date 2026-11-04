#!/usr/bin/env python3
"""callcheck: run cgcallers on every function or method a diff removes, renames or gives a new signature.

    python3 -I callcheck.py [-p W] --cached          the staged diff (before a commit)
    python3 -I callcheck.py [-p W] <base>..<head>    a commit range (the controller, at each stop)
    python3 -I callcheck.py --selftest

It compares the definitions of each changed Python or JS/TS file on both sides of the diff (Python by its AST,
JS/TS by a pattern for `function f(`, `f = (...) =>` and a method `f(...) {`). For each name it prints the
cgcallers block of that file's definition; for a name no definition holds any more (removed, renamed) it prints
the word hits cgcallers' search finds in the tracked files of that language. The last line counts the names checked
and the caller lines to read.
"""
import ast
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cgcallers  # noqa: E402  (the word search and the marks are cgcallers' own)

PY = (".py",)
JS = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx")
# shortcut: a JS/TS signature is read from one line; a parameter list over several lines is not compared
JS_DEF = [re.compile(p, re.M) for p in (
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*(\w+)\s*(?:<[^>]*>)?\s*\(([^)]*)\)",
    r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:function\b[^(]*)?\(([^)]*)\)",
    r"^[ \t]+(?:(?:public|private|protected|static|async|override|readonly)\s+)*(\w+)\s*(?:<[^>]*>)?\s*\(([^)]*)\)\s*(?::\s*[^{;]+)?\{")]
NOT_NAMES = {"if", "for", "while", "switch", "catch", "function", "return", "constructor", "with"}


def git(W, *args, missing_ok=False):
    """git's stdout; a failure stops with git's own words (missing_ok: a path absent on one side gives "")."""
    p = subprocess.run(["git", "-C", W] + list(args), capture_output=True, text=True)
    if p.returncode and not missing_ok:
        sys.exit("callcheck: git %s failed: %s" % (" ".join(args), p.stderr.strip()))
    return p.stdout if p.returncode == 0 else ""


def defs(src, path):
    """{name: signature} of the functions and methods in a source; a method is Class.name."""
    out = {}
    if path.endswith(PY):
        try:
            tree = ast.parse(src)
        except SyntaxError:
            return out

        def walk(node, prefix):
            for n in ast.iter_child_nodes(node):
                if isinstance(n, ast.ClassDef):
                    walk(n, prefix + n.name + ".")
                elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out[prefix + n.name] = "(%s)" % ast.unparse(n.args)
                    walk(n, prefix + n.name + ".")
        walk(tree, "")
        return out
    for rx in JS_DEF:
        for m in rx.finditer(src):
            if m.group(1) not in NOT_NAMES:
                out.setdefault(m.group(1), "(%s)" % " ".join(m.group(2).split()))
    return out


def changes(W, spec):
    """[(kind, name, file, note)] for each removed, renamed or re-signed function in the diff."""
    cached = spec == "--cached"
    base, head = ("HEAD", "") if cached else spec.split("..", 1)
    diff = git(W, "diff", "--name-status", "-M", *(["--cached"] if cached else [base, head]))
    out = []
    for row in diff.splitlines():
        parts = row.split("\t")
        status, old = parts[0], parts[1]
        new = parts[-1]
        if not old.endswith(PY + JS) or status.startswith("A"):
            continue
        before = defs(git(W, "show", "%s:%s" % (base, old), missing_ok=True), old)
        after = {} if status.startswith("D") else defs(git(W, "show", "%s:%s" % (head, new), missing_ok=True), new)
        added = {n: s for n, s in after.items() if n not in before}
        for name, sig in before.items():
            if name in after:
                if after[name] != sig:
                    out.append(("signature", name, new, "%s -> %s" % (sig, after[name])))
                continue
            twin = [n for n, s in added.items() if s == sig and n.rsplit(".", 1)[0:-1] == name.rsplit(".", 1)[0:-1]]
            out.append(("renamed", name, old, "to " + twin[0]) if len(twin) == 1 else ("removed", name, old, ""))
    return out


def run_cgcallers(W, name, path, script=os.path.join(HERE, "cgcallers.py")):
    p = subprocess.run([sys.executable, "-I", script, name, "-p", W, "-f", path], capture_output=True, text=True)
    return p.stdout + ("\n[cgcallers failed] exit %d: %s" % (p.returncode, p.stderr.strip()[-500:]) if p.returncode else "")


def word_hits(W, name, path):
    """The code lines that still name a function no definition holds, by cgcallers' own rules: the word search in
    its file and the files that import its module (any file for a method), with no namesake's def line."""
    word, ext = name.rsplit(".", 1)[-1], (PY if path.endswith(PY) else JS)
    lang = "python" if ext == PY else "typescript"
    mod, pkg = cgcallers.module_of(path), os.path.basename(os.path.dirname(path))
    wanted = {"mod:" + mod, "name:" + mod, "imp:" + pkg, "from:%s:%s" % (pkg, word)}
    method = "." in name
    rows = []
    for f in git(W, "ls-files").splitlines():
        if f.endswith(ext):
            try:
                src = cgcallers.read_file(os.path.join(W, f))
            except OSError:
                continue
            if f != path and not method and not wanted & cgcallers.imported(src, lang):
                continue
            body = src.splitlines()
            for ln in cgcallers.word_lines(src, lang, word):
                line = body[ln - 1].strip()
                if not re.search(r"\b(def|function)\s*\*?\s*%s\b" % re.escape(word), line):
                    rows.append("[grep only] %s:%d  %s" % (f, ln, line[:110]))
    return rows


def check(W, spec, callers=run_cgcallers):
    found = changes(W, spec)
    lines = []
    for kind, name, path, note in found:
        lines.append("\n== %s: %s (%s)%s" % (kind, name, path, " " + note if note else ""))
        text = callers(W, name, path)
        if kind != "signature" and ("no definition named" in text or "matches file" in text):   # none left in this file
            text += "\n".join(["word search (no definition holds %s any more):" % name] + word_hits(W, name, path))
        lines.append(text.rstrip())
    to_read = sum(l.startswith("[") for t in lines for l in t.splitlines())
    lines.append("\ncallcheck: %d names checked (removed, renamed or re-signed), %d caller lines to read" % (len(found), to_read))
    return "\n".join(lines)


def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as W:
        g = lambda *a: subprocess.run(["git", "-C", W] + list(a), check=True, capture_output=True)
        g("init", "-q")
        g("config", "user.name", "t")
        g("config", "user.email", "t@t")
        files = {"a.py": "def gone():\n    return 1\n\n\ndef old_name(x):\n    return x\n\n\ndef resigned(a):\n    return a\n\n\n"
                         "def same():\n    return 0\n\n\nclass K:\n    def ack(self):\n        return 1\n\n\n"
                         "class L:\n    def ack(self):\n        return 2\n",
                 "f.py": "def g(o):\n    return o.ack()\n",
                 "b.py": "from a import gone, same\n\n\ndef use():\n    return gone() + same()  # gone\n",
                 "c.ts": "export function gone2(n: number) {\n  return n\n}\n",
                 "d.py": "def gone():\n    return 2\n",                         # a namesake: its def is no caller
                 "e.py": "def other():\n    return gone()\n"}                    # no import of a: not this function's
        for f, body in files.items():
            with open(os.path.join(W, f), "w") as fh:
                fh.write(body)
        g("add", ".")
        g("commit", "-qm", "one")
        with open(os.path.join(W, "a.py"), "w") as fh:
            fh.write("def new_name(x):\n    return x\n\n\ndef resigned(a, b):\n    return a\n\n\ndef same():\n    return 0\n\n\n"
                     "class L:\n    def ack(self):\n        return 2\n")
        with open(os.path.join(W, "c.ts"), "w") as fh:
            fh.write("export const keep = 1\n")
        g("add", ".")
        asked = []

        def fake(W_, name, path):
            asked.append((name, path))
            if name in ("gone", "K.ack"):       # a namesake left: codegraph shows the other definitions instead
                return ('codegraph: no definition of "%s" matches file "a.py" — showing all definitions instead.\n'
                        "definition  d.py:1  function gone" % name)
            return ("codegraph: no definition named %s" % name if name in ("gone2", "old_name")
                    else "definition  %s:1  function %s\n[both     ] x.py:9  f  %s()" % (path, name, name))

        for spec in ("--cached", None):
            if spec is None:
                g("commit", "-qm", "two")
                spec = "HEAD~1..HEAD"
            asked.clear()
            out = check(W, spec, fake)
            assert sorted(asked) == [("K.ack", "a.py"), ("gone", "a.py"), ("gone2", "c.ts"), ("old_name", "a.py"),
                                     ("resigned", "a.py")], asked
            assert "== removed: gone (a.py)" in out and "== renamed: old_name (a.py) to new_name" in out, out
            assert "== signature: resigned (a.py) (a) -> (a, b)" in out and "== removed: gone2 (c.ts)" in out, out
            assert "same" not in [n for n, p in asked], asked                      # an unchanged function: no block
            assert "[grep only] b.py:5  return gone() + same()  # gone" in out, out  # a caller of a removed function
            assert "b.py:1" in out, out                                               # its import line
            assert "[grep only] d.py" not in out and "e.py" not in out, out           # R13: a namesake's def; R1: no import
            assert "[grep only] f.py:2  return o.ack()" in out and "[grep only] a.py" not in out, out   # a method: any file
            assert out.splitlines()[-1] == "callcheck: 5 names checked (removed, renamed or re-signed), 4 caller lines to read", out
        try:                                                                          # R2: a bad range stops with git's words
            check(W, "nosuch..HEAD", fake)
            raise AssertionError("a bad range must stop")
        except SystemExit as e:
            assert "nosuch" in str(e), e
        boom = os.path.join(W, "boom.py")
        with open(boom, "w") as fh:
            fh.write("import sys\nprint('partial')\nsys.exit('Traceback: boom')\n")
        out = run_cgcallers(W, "x", "a.py", script=boom)                             # R2: a crashed cgcallers is a line to read
        assert "partial" in out and "[cgcallers failed] exit 1: Traceback: boom" in out, out
    print("callcheck selftest ok")
    return 0


def main(argv):
    if argv[1:] == ["--selftest"]:
        return selftest()
    args = argv[1:]
    W = args[args.index("-p") + 1] if "-p" in args else git(os.getcwd(), "rev-parse", "--show-toplevel").strip()
    spec = [a for i, a in enumerate(args) if a != "-p" and (i == 0 or args[i - 1] != "-p")]
    if len(spec) != 1 or not (spec[0] == "--cached" or ".." in spec[0]):
        sys.exit(__doc__)
    print(check(W, spec[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
