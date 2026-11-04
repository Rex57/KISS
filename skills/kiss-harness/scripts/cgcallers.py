#!/usr/bin/env python3
"""cgcallers: who calls NAME, from `codegraph callers` AND a word search, so a CodeGraph blind spot shows.

    python3 -I cgcallers.py NAME [-p W] [-f FILE] [--all]
    python3 -I cgcallers.py --selftest

It syncs W's index first. Then, for each definition of NAME (only the one in FILE with -f, a path or suffix, as
`codegraph callers -f` does), it prints a block: the definition, its caller lines and a count line. The word search
reads only that definition's own file and the files that import its module or its package (Python `import` /
`from ... import` / `importlib.import_module`; JS/TS/Svelte `import ... from` a path that ends in either); for a
method, and with --all, it reads every indexed file of the language. A hit in a comment, a string or a docstring is
not counted. For a language with no import filter it reads every indexed file of that language and prints a warning. codegraph misses a function passed as a value, a call through getattr
with a string, a method on an object when two classes define the name, and recursion (KISS rules/codegraph.md,
"callers is incomplete"). Each caller line is marked:
  [both]       codegraph has an edge on this line and the word search finds the name on it
  [grep only]  the name on a line with no codegraph edge: a caller codegraph missed, an import, or a namesake: read it
  [cg only]    a codegraph edge on a line the word search does not find (an alias such as `F.name`)
  [cg guess]   a codegraph edge with confidence 0.4 resolved by exact name match: a guess from the name only
"""
import argparse
import ast
import io
import json
import os
import re
import subprocess
import sys
import tokenize

PY = {"python"}
JS = {"javascript", "typescript", "tsx", "jsx", "svelte"}
IMPORT_MODULE = re.compile(r"""import_module\(\s*['"]([\w.]+)['"]""")
IMPORT_FROM = re.compile(r"""(?:\bfrom|\bimport|\brequire)\s*\(?\s*['"]([^'"]+)['"]""")


def def_spans(src):
    """[(first line, last line, name)] of every def and class in a Python source; [] if it does not parse."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    return [(n.lineno, n.end_lineno, n.name) for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]


def enclosing(spans, line):
    """The innermost def or class around `line`, or '<module>'."""
    inside = [s for s in spans if s[0] <= line <= s[1]]
    return max(inside, key=lambda s: s[0])[2] if inside else "<module>"


def module_of(path):
    """The name an import uses for this file: its stem, or its folder for __init__.py and index.*."""
    stem = os.path.splitext(os.path.basename(path))[0]
    return os.path.basename(os.path.dirname(path)) if stem in ("__init__", "index") else stem


def imported(src, lang):
    """The module names this source imports: the last part of each module path, each name a from-import takes
    (a module of a package), and each importlib.import_module("...") string."""
    if lang in JS:
        return {module_of(p) for p in IMPORT_FROM.findall(src)}
    names = {m.split(".")[-1] for m in IMPORT_MODULE.findall(src)}
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return names | {w for l in re.findall(r"^\s*(?:from|import)\s.*$", src, re.M) for w in re.findall(r"\w+", l)}
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            names |= {(n.module or "").split(".")[-1]} | {a.name for a in n.names}
        elif isinstance(n, ast.Import):
            names |= {a.name.split(".")[-1] for a in n.names}
    return names


def code_only(src, quotes="'\"`"):
    """src with // and /* */ comments and string bodies blanked (newlines kept); code inside `${...}` stays.
    shortcut: a regex literal holding a quote blanks up to the line end, and # comments are kept; fine for a word search."""
    out = list(src)

    def blank(a, b):
        for k in range(a, min(b, len(src))):
            if out[k] != "\n":
                out[k] = " "

    def code(i, nested):                    # nested: inside `${...}`, return after its closing brace
        depth = 0
        while i < len(src):
            if src.startswith("//", i):
                j = src.find("\n", i)
                j = len(src) if j < 0 else j
                blank(i, j)
                i = j
            elif src.startswith("/*", i):
                j = src.find("*/", i + 2)
                j = len(src) if j < 0 else j + 2
                blank(i, j)
                i = j
            elif src[i] in quotes:
                i = string(i + 1, src[i])
            else:
                if nested and src[i] == "{":
                    depth += 1
                elif nested and src[i] == "}":
                    if not depth:
                        return i + 1
                    depth -= 1
                i += 1
        return i

    def string(i, q):
        start = i
        while i < len(src) and src[i] != q:
            if src[i] == "\\":
                i += 2
            elif q == "`" and src.startswith("${", i):
                blank(start, i)
                i = code(i + 2, True)
                start = i
            elif q != "`" and src[i] == "\n":
                break                           # an unclosed quote ends at the line
            else:
                i += 1
        blank(start, i)
        return i + 1

    code(0, False)
    return "".join(out)


def word_lines(src, lang, name):
    """The lines where NAME is a word of code, not of a comment, a string or a docstring; in Python also the
    string 'NAME' given to getattr, hasattr or setattr (a call CodeGraph cannot see)."""
    if lang in PY:
        found = set()
        try:
            for t in tokenize.generate_tokens(io.StringIO(src).readline):
                if t.type == tokenize.NAME and t.string == name or (
                        t.type == tokenize.STRING and t.string[1:-1] == name and re.search(r"\b(get|set|has)attr\s*\(", t.line)):
                    found.add(t.start[0])
        except (tokenize.TokenError, SyntaxError):
            pass
        return sorted(found)
    rx = re.compile(r"\b%s\b" % re.escape(name))
    text = code_only(src, "'\"`" if lang in JS else "\"`")
    return [i for i, t in enumerate(text.splitlines(), 1) if rx.search(t)]


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True).stdout


def read_file(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def main(argv=None, cg=None, git=None, read=read_file):
    """cg(args) and git(args) run `codegraph ARGS` and `git ARGS` in W and return stdout; read(path) returns a file."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("name", nargs="?")
    ap.add_argument("-p", dest="W", help="the checkout (default: git toplevel of this folder)")
    ap.add_argument("-f", dest="file", help="only the definition in this file")
    ap.add_argument("--all", action="store_true", help="search every indexed file of the language, not only importers")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.name:
        ap.error("NAME is required")
    git = git or (lambda args: run(["git"] + args, os.getcwd()))
    W = a.W or git(["rev-parse", "--show-toplevel"]).strip()
    cg = cg or (lambda args: run(["codegraph"] + args, W))
    said = [l.strip("│●└┌◇◆ ") for l in cg(["sync", W]).splitlines()]
    said = [l for l in said if l and l not in ("Syncing CodeGraph", "Done", "Scanning files...")]
    print("codegraph sync: %s" % (said[-1] if said else "no output (is codegraph on PATH?)"))
    try:
        found = json.loads(cg(["callers", "-p", W, "-j", "-l", "2000"] + (["-f", a.file] if a.file else []) + [a.name]) or "{}")
    except json.JSONDecodeError:
        found = {}
    defs = found.get("definitions") or []
    if not defs:
        print("codegraph: no definition named %s in %s (check the name, the index: codegraph status \"%s\")" % (a.name, W, W))
        return 0
    try:
        indexed = [(f["path"], f.get("language", "")) for f in json.loads(cg(["files", "-p", W, "-j"]) or "[]")]
    except json.JSONDecodeError:
        indexed = []
    texts, imports, scans, warned = {}, {}, {}, set()

    def text(f):
        if f not in texts:
            try:
                texts[f] = read(os.path.join(W, f))
            except OSError:
                texts[f] = ""
        return texts[f]

    def names(f, lang):                     # each file parsed once, for every definition
        if f not in imports:
            imports[f] = imported(text(f), lang)
        return imports[f]

    def scan(f, lang):                      # (word lines, def spans) of a file, once for every definition
        if f not in scans:
            scans[f] = (word_lines(text(f), lang, word), def_spans(text(f)) if lang in PY else [])
        return scans[f]

    word = a.name
    n = re.escape(word)
    for d in defs:
        dd = d["definition"]
        home, lang = dd["filePath"], dd.get("language", "")
        print("\ndefinition  %s:%s  %s %s" % (home, dd["startLine"], dd.get("kind", ""), dd["name"]))
        family = PY if lang in PY else JS if lang in JS else {lang}
        if not family & (PY | JS) and lang not in warned:
            warned.add(lang)
            print("warning: no import filter for %s: searched every indexed %s file" % (lang, lang))
        # its module, and its package: `from pkg import name` reaches a name pkg/__init__ re-exports
        mods = {module_of(home), os.path.basename(os.path.dirname(home))} - {""}
        # a method is called on an object, whose file seldom imports the class's module: no import filter
        files = [f for f, l in indexed if l in family and (f == home or a.all or not family & (PY | JS)
                                                            or dd.get("kind") == "method"
                                                            or mods & names(f, l))]
        langs = dict(indexed)
        who_cg = {c["id"]: c for c in d.get("callers") or []}
        edges = {}   # (file, line) -> (caller name, a guess?)
        for e in d.get("edges") or []:
            c, m = who_cg.get(e.get("source"), {}), e.get("metadata") or {}
            if c:
                edges[(c["filePath"], e.get("line") or c.get("startLine"))] = (
                    c["name"], m.get("confidence") == 0.4 and m.get("resolvedBy") == "exact-match")
        rows, matched = [], set()
        for f in files:
            body = text(f).splitlines()
            hits, spans = scan(f, langs.get(f))
            for ln in hits:
                line = body[ln - 1].strip() if ln <= len(body) else ""
                if (f == home and ln == dd["startLine"]) or re.search(r"\b(def|function)\s*\*?\s*%s\b" % n, line):
                    continue                       # this definition, or a namesake's
                if (f, ln) in edges:
                    matched.add((f, ln))
                    who, guess = edges[(f, ln)]
                    rows.append(("cg guess" if guess else "both", f, ln, who, line[:110]))
                else:
                    rows.append(("grep only", f, ln, enclosing(spans, ln) if spans else "-", line[:110]))
        for (f, ln), (who, guess) in edges.items():
            if (f, ln) not in matched:
                rows.append(("cg guess" if guess else "cg only", f, ln or 0, who, ""))
        rows.sort(key=lambda r: (r[0] != "grep only", r[1].startswith("tests/"), r[1], r[2]))
        for mark, f, ln, who, line in rows:
            print("[%-9s] %s:%s  %s  %s" % (mark, f, ln, who, line))
        g = [r for r in rows if r[0] == "grep only"]
        print("%d codegraph callers; %d grep-only lines (%d outside tests): read each before you trust a count."
              % (len({(c["filePath"], c["name"]) for c in who_cg.values()}), len(g), sum(not r[1].startswith("tests/") for r in g)))
    return 0


def selftest():
    import contextlib, io, tempfile
    src = "def a():\n    x = 1\n    def b():\n        return f()\n    return b\n\nclass C:\n    def m(self):\n        return f()\n\nf()\n"
    sp = def_spans(src)
    assert enclosing(sp, 4) == "b", sp          # the innermost def wins
    assert enclosing(sp, 2) == "a"
    assert enclosing(sp, 9) == "m"
    assert enclosing(sp, 11) == "<module>"
    assert def_spans("def (") == []             # a file that does not parse
    files = {
        "lib/util.py": "def helper():\n    return 1\n",
        "lib/more.py": "def helper():\n    return 2\n",
        "app.py": ("from lib.util import helper\n\ndef go():\n    # helper is called below\n    s = \"helper\"\n"
                   "    return helper()\n\ndef go2():\n    return helper()\n"),
        "other.py": "def elsewhere():\n    return helper()\n",
        "web/api.ts": "export function fetchIt() {}\n",
        "web/page.ts": ("import { fetchIt } from './api'\n// fetchIt in a comment\nconst s = 'fetchIt';\nfetchIt();\n"
                        "function x() { fetchIt(); }\nconst t = `a ${fetchIt()} b`;\n"),
        "web/stray.ts": "fetchIt();\n",
        "web/own.ts": "import { fetchIt as f } from './api'\nexport function fetchIt() {}\n",
        "svc/serve.go": "package svc\n\nfunc Serve() {}\n",
        "lib/eng.py": "class Engine:\n    def ack(self):\n        return 1\n\nclass Other:\n    def ack(self):\n        return 2\n",
        "user.py": "def go3(e):\n    return e.ack()\n",
        "pkg/__init__.py": "from .util import helper2\n",
        "pkg/util.py": "def helper2():\n    return 1\n",
        "routes.py": "from pkg import helper2\nROUTES = [(\"GET\", helper2)]\nf = getattr(pkg, 'helper2', None)\n",
        "lazy.py": "import importlib\nm = importlib.import_module(\"pkg.util\")\nm.helper2()\n",
        "svc/main.go": "package svc\n\nfunc main() { Serve() }\n",
    }
    lang = {".py": "python", ".ts": "typescript", ".go": "go"}
    d_ = lambda f, n, line, lg, kind="function": {"name": n, "kind": kind, "filePath": f, "startLine": line, "id": "def:" + f, "language": lg}
    edge = lambda f, who, line, conf=0.9: ({"id": "c:%s:%s" % (f, who), "name": who, "kind": "function", "filePath": f, "startLine": 1},
                                           {"source": "c:%s:%s" % (f, who), "line": line,
                                            "metadata": {"confidence": conf, "resolvedBy": "exact-match"}})
    defs = {"helper": [(d_("lib/util.py", "helper", 1, "python"), [edge("app.py", "go", 6)] + [edge("app.py", "go2", 9, 0.4)]),
                       (d_("lib/more.py", "helper", 1, "python"), [])],
            "fetchIt": [(d_("web/api.ts", "fetchIt", 1, "typescript"), [edge("web/page.ts", "x", 5)])],
            "Serve": [(d_("svc/serve.go", "Serve", 3, "go"), [])],
            "helper2": [(d_("pkg/util.py", "helper2", 1, "python"), [])],
            "ack": [(d_("lib/eng.py", "ack", 2, "python", "method"), []), (d_("lib/eng.py", "ack", 6, "python", "method"), [])]}
    calls = []

    def fake_cg(args):
        calls.append(args[0])
        if args[0] == "sync":
            return "┌  Syncing CodeGraph\n│\n●  Already up to date\n│\n└  Done\n"
        if args[0] == "files":
            return json.dumps([{"path": f, "language": lang[os.path.splitext(f)[1]]} for f in files])
        name, only = args[-1], (args[args.index("-f") + 1] if "-f" in args else None)
        out = [{"definition": dd, "callers": [c for c, e in es], "edges": [e for c, e in es]}
               for dd, es in defs.get(name, []) if not only or dd["filePath"].endswith(only)]
        return json.dumps({"definitions": out})

    with tempfile.TemporaryDirectory() as W:
        for f, body in files.items():
            os.makedirs(os.path.dirname(os.path.join(W, f)), exist_ok=True)
            with open(os.path.join(W, f), "w") as fh:
                fh.write(body)
        subprocess.run(["git", "init", "-q"], cwd=W, check=True)

        def out(*argv, git=None):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                main(list(argv), cg=fake_cg, git=git)
            return buf.getvalue()

        o = out("helper", "-p", W)
        lines = o.splitlines()
        assert lines[0] == "codegraph sync: Already up to date", lines[:2]    # the sync result comes first
        assert calls[0] == "sync", calls
        assert sum(l.startswith("definition") for l in lines) == 2, o                      # one block per definition
        assert "[both     ] app.py:6  go  return helper()" in lines, o                     # an importer's call
        assert "[cg guess ] app.py:9  go2  return helper()" in lines, o                    # a 0.4 exact-match edge
        assert "other.py" not in o, o                                                      # no import: not shown
        assert "app.py:4" not in o and "app.py:5" not in o, o                              # comment and string
        assert o.count("codegraph callers;") == 2, o                                       # a count line per block
        o = out("helper", "-p", W, "-f", "lib/more.py")
        assert sum(l.startswith("definition") for l in o.splitlines()) == 1 and "lib/more.py" in o, o
        o = out("fetchIt", "-p", W)
        lines = o.splitlines()
        assert "[grep only] web/page.ts:4  -  fetchIt();" in lines, o                      # a JS call CodeGraph misses
        assert "[both     ] web/page.ts:5  x  function x() { fetchIt(); }" in lines, o
        assert any(l.startswith("[grep only] web/page.ts:6") for l in lines), o            # code inside ${...}
        assert "page.ts:2" not in o and "page.ts:3" not in o and "stray.ts" not in o, o
        assert "own.ts:2" not in o, o                                                      # a namesake's definition
        o = out("Serve", git=lambda args: W)                                               # W from git
        assert "warning: no import filter for go: searched every indexed go file" in o, o
        assert "[grep only] svc/main.go:3" in o, o
        o = out("ack", "-p", W)
        assert o.count("[grep only] user.py:2  go3  return e.ack()") == 2, o              # F1: a method's caller needs no import
        o = out("helper2", "-p", W)
        assert "[grep only] routes.py:3  -  f = getattr(pkg, 'helper2', None)" in o, o   # F3: getattr with a string
        assert "[grep only] routes.py:2  -  ROUTES" in o and "[grep only] lazy.py:3  -  m.helper2()" in o, o   # F2: via the package
    assert code_only("a('x // y') // z\n/* q\n */ b(\"c\")") == "a('      ')     \n    \n    b(\" \")"
    print("cgcallers selftest ok")
    return 0

if __name__ == "__main__":
    sys.exit(main())
