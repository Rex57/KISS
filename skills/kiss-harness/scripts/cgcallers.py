#!/usr/bin/env python3
"""cgcallers: who calls NAME, from `codegraph callers` AND a word grep, so a CodeGraph blind spot shows.

    python3 -I cgcallers.py NAME [-p W] [-f FILE] [--all]
    python3 -I cgcallers.py --selftest

codegraph misses a call after `import X` inside a function, to a function named get or copy, to a function
passed as a value (route tables, callbacks), through getattr with a string, through a local alias, and
recursion (KISS rules/codegraph.md, "callers is incomplete"). Each caller line is marked:
  [both]       codegraph and the grep agree
  [grep only]  a caller codegraph missed, OR a mention (route table, string, comment) OR another NAME: read it
  [cg only]    codegraph has it, the word grep does not (an alias such as `F.name`, or a renamed import)
-f narrows to the definition in FILE (path or suffix), as `codegraph callers -f` does. For a common name
(get, copy, build, ...) the grep only matches `<module>.NAME` and `from <module> import NAME`; --all drops that.
"""
import argparse
import ast
import json
import os
import re
import subprocess
import sys

COMMON = {"get", "copy", "update", "items", "keys", "values", "pop", "set", "add", "run", "build", "read",
          "write", "close", "open", "start", "stop", "main", "check", "load", "save", "send", "put", "call"}
CODE = ("*.py", "*.js", "*.jsx", "*.ts", "*.tsx", "*.svelte", ":!docs", ":!archive")


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


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True).stdout


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("name", nargs="?")
    ap.add_argument("-p", dest="W", help="the checkout (default: git toplevel of this folder)")
    ap.add_argument("-f", dest="file", help="narrow to the definition in this file")
    ap.add_argument("--all", action="store_true", help="word grep even for a common name")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.name:
        ap.error("NAME is required")
    W = a.W or run(["git", "rev-parse", "--show-toplevel"], os.getcwd()).strip()
    cmd = ["codegraph", "callers", "-p", W, "-j", "-l", "2000"] + (["-f", a.file] if a.file else []) + [a.name]
    try:
        cg = json.loads(run(cmd, W) or "{}")
    except json.JSONDecodeError:
        cg = {}
    defs = cg.get("definitions") or []
    if not defs:
        print("codegraph: no definition named %s in %s (check the name, the index: codegraph status \"%s\")" % (a.name, W, W))
    seen = {}   # (file, caller name) -> line, from codegraph
    for d in defs:
        dd = d["definition"]
        print("definition  %s:%s  %s %s" % (dd["filePath"], dd["startLine"], dd.get("kind", ""), dd["name"]))
        for c in d.get("callers") or []:
            seen[(c["filePath"], c["name"])] = c.get("startLine")
    def_lines = {(d["definition"]["filePath"], d["definition"]["startLine"]) for d in defs}
    stems = sorted({os.path.splitext(os.path.basename(d["definition"]["filePath"]))[0] for d in defs})
    n = re.escape(a.name)
    if a.name in COMMON and stems and not a.all:
        s = "|".join(map(re.escape, stems))
        pattern = r"\b(%s)\.%s\b|from \S*\b(%s) import .*\b%s\b" % (s, n, s, n)
    else:
        pattern = r"\b%s\b" % n
    hits, rx = [], re.compile(pattern)
    # Python's re, not `git grep -E`: the macOS git has no \b in its ERE, so it silently matched nothing.
    for f in run(["git", "ls-files", "--"] + list(CODE), W).splitlines():
        try:
            lines = open(os.path.join(W, f), encoding="utf-8", errors="replace").read().splitlines()
        except OSError:
            continue
        hits += [(f, i, t.strip()) for i, t in enumerate(lines, 1) if rx.search(t)]
    spans = {}
    rows, matched = [], set()
    for f, ln, text in hits:
        if (f, ln) in def_lines or re.match(r"\s*(async\s+)?def\s+%s\b" % n, text):
            continue                       # the definition itself
        if f.endswith(".py"):
            if f not in spans:
                try:
                    spans[f] = def_spans(open(os.path.join(W, f), encoding="utf-8").read())
                except OSError:
                    spans[f] = []
            who = enclosing(spans[f], ln)
            key = (f, who)
        else:                              # js/svelte: codegraph names functions or components; match the file
            who = "-"
            key = next((k for k in seen if k[0] == f), (f, "-"))
        mark = "both" if key in seen else "grep only"
        if key in seen:
            matched.add(key)
        rows.append((mark, f, ln, who, text[:110]))
    for (f, who), ln in seen.items():
        if (f, who) not in matched:
            rows.append(("cg only", f, ln or 0, who, ""))
    rows.sort(key=lambda r: (r[0] != "grep only", r[1].startswith("tests/"), r[1], r[2]))
    for mark, f, ln, who, text in rows:
        print("[%-9s] %s:%s  %s  %s" % (mark, f, ln, who, text))
    g = [r for r in rows if r[0] == "grep only"]
    print("\n%d codegraph callers; %d grep-only lines (%d outside tests): read each before you trust a count."
          % (len(seen), len(g), sum(not r[1].startswith("tests/") for r in g)))
    return 0


def selftest():
    src = "def a():\n    x = 1\n    def b():\n        return f()\n    return b\n\nclass C:\n    def m(self):\n        return f()\n\nf()\n"
    sp = def_spans(src)
    assert enclosing(sp, 4) == "b", sp          # the innermost def wins
    assert enclosing(sp, 2) == "a"
    assert enclosing(sp, 9) == "m"
    assert enclosing(sp, 11) == "<module>"
    assert def_spans("def (") == []             # a file that does not parse
    assert re.search(r"\bcount_day\b", "register.count_day(conn)")   # the word pattern the scan uses
    print("cgcallers selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
