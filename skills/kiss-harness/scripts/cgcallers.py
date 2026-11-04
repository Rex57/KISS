#!/usr/bin/env python3
"""cgcallers: who calls NAME, from `codegraph callers` AND a word search, so a CodeGraph blind spot shows.

    python3 -I cgcallers.py NAME [-p W] [-f FILE] [--all]
    python3 -I cgcallers.py --selftest

It stops when W has no index of its own, and syncs W's index first. Then, for each definition of NAME (a bare name
or Class.method; only the one in FILE with -f, a path or suffix, as `codegraph callers -f` does), it prints a block:
the definition, its caller lines and a count line. The word search (for the last part of NAME) reads only that
definition's own file and the files that import its module or its package (Python `import` / `from ... import` /
`importlib.import_module`; JS/TS/Svelte `import ... from` a path that ends in either); for a method, and with --all,
it reads every indexed file of the language. A hit in a comment, a string or a docstring is not counted, except the
string 'NAME' given to getattr, hasattr or setattr. For a function (not a method), a hit `X.NAME` counts only when X
is its module or a name bound to it (`import a.b as X`, `X = import_module(...)`). For a language with no import
filter it reads every indexed file of that language and prints a warning. codegraph misses a function passed as a
value, a call through getattr with a string, a method on an object when two classes define the name, and recursion
(KISS rules/codegraph.md, "callers is incomplete").
With pyright-langserver (Python) or typescript-language-server (JS/TS) on PATH, an LSP pass asks the server for the
references of each definition (one deadline of 120 s for the whole pass, then "LSP: timed out"); with no server it
prints "no language server for <language>: LSP pass skipped".
Each caller line is marked:
  [both]       codegraph has an edge on this line and the word search finds the name on it, or (Python) the line is
               in a function codegraph lists as a caller
  [grep only]  the name on a line with no codegraph edge: a caller codegraph missed, an import, or a namesake: read it
  [cg only]    a codegraph edge on a line the word search does not find (an alias such as `F.name`)
  [cg guess]   a codegraph edge with confidence 0.4 resolved by exact name match: a guess from the name only
  [lsp]        a reference the language server found and codegraph did not list (also a grep line it confirms)
"""
import argparse
import ast
import io
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import tokenize
import urllib.parse

PY = {"python"}
JS = {"javascript", "typescript", "tsx", "jsx", "svelte"}
# the language servers of the LSP pass, started over stdio when on PATH (D5); the whole pass stops after LSP_LIMIT s
SERVERS = {"python": ["pyright-langserver", "--stdio"], "js": ["typescript-language-server", "--stdio"]}
LSP_LIMIT = 120
LSP_IDS = {"python": "python", "javascript": "javascript", "jsx": "javascriptreact", "typescript": "typescript",
           "tsx": "typescriptreact"}
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
    """What this source imports, as tags: mod:M (a module path that ends in M, or an import_module string),
    name:N (a name a from-import takes, maybe a module of a package), imp:P (`import ... P`), and from:P:N (N taken
    from P, as a re-export of a package's __init__ or index)."""
    if lang in JS:
        tags = {"mod:" + module_of(p) for p in IMPORT_FROM.findall(src)}
        for names, p in re.findall(r"""\bimport\s*(?:type\s*)?\{([^}]*)\}\s*from\s*['"]([^'"]+)['"]""", src):
            tags |= {"from:%s:%s" % (module_of(p), n.split(" as ")[0].strip()) for n in names.split(",")}
        return tags
    tags = {"mod:" + m.split(".")[-1] for m in IMPORT_MODULE.findall(src)}
    try:
        tree = ast.parse(src)
    except SyntaxError:
        words = {w for l in re.findall(r"^\s*(?:from|import)\s.*$", src, re.M) for w in re.findall(r"\w+", l)}
        return tags | {k + w for k in ("mod:", "name:", "imp:") for w in words}
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            m = (n.module or "").split(".")[-1]
            tags |= {"mod:" + m} | {"name:" + a.name for a in n.names} | {"from:%s:%s" % (m, a.name) for a in n.names}
        elif isinstance(n, ast.Import):
            tags |= {k + a.name.split(".")[-1] for a in n.names for k in ("mod:", "imp:")}
    return tags


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
    """{line: [receiver, ...]} where NAME is a word of code, not of a comment, a string or a docstring; the receiver
    is the word before `.NAME` ('?' for an expression), None for a bare NAME. In Python also the string 'NAME' given
    to getattr, hasattr or setattr (a call CodeGraph cannot see), with no receiver."""
    found = {}
    if lang in PY:
        last = []                               # the two code tokens before this one
        try:
            for t in tokenize.generate_tokens(io.StringIO(src).readline):
                if t.type in (tokenize.NL, tokenize.NEWLINE, tokenize.COMMENT, tokenize.INDENT, tokenize.DEDENT):
                    continue
                if t.type == tokenize.NAME and t.string == name:
                    dot = len(last) == 2 and last[1].string == "."
                    found.setdefault(t.start[0], []).append(
                        (last[0].string if last[0].type == tokenize.NAME else "?") if dot else None)
                elif t.type == tokenize.STRING and t.string[1:-1] == name and re.search(r"\b(get|set|has)attr\s*\(", t.line):
                    found.setdefault(t.start[0], []).append(None)
                last = (last + [t])[-2:]
        except (tokenize.TokenError, SyntaxError):
            pass
        return found
    rx = re.compile(r"\b%s\b" % re.escape(name))
    for i, t in enumerate(code_only(src, "'\"`" if lang in JS else "\"`").splitlines(), 1):
        for m in rx.finditer(t):
            before = t[:m.start()]
            dot = re.search(r"(\w*)\s*\??\.\s*$", before) if not before.rstrip().endswith("...") else None
            found.setdefault(i, []).append((dot.group(1) or "?") if dot else None)
    return found


def aliases(src, lang):
    """{local name: module} for each module bound to another name: `import a.b as X`, `from a import b as X`,
    `X = importlib.import_module("a.b")`, JS `import * as X from './b'` and `import X from './b'`."""
    if lang in JS:
        return {x: module_of(p) for x, p in re.findall(r"""\bimport\s+(?:\*\s+as\s+)?(\w+)\s+from\s*['"]([^'"]+)['"]""", src)}
    out = {x: m.split(".")[-1] for x, m in re.findall(r"""(\w+)\s*=\s*[\w.]*import_module\(\s*['"]([\w.]+)['"]""", src)}
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    for n in ast.walk(tree):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            out.update({x.asname: x.name.split(".")[-1] for x in n.names if x.asname})
    return out


class Lsp:
    """One language server over stdio: framed JSON-RPC, a reader thread, and replies to the server's own requests."""

    def __init__(self, argv, W):
        self.p = subprocess.Popen(argv, cwd=W, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.q, self.n, self.checked = queue.Queue(), 0, set()
        threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        f = self.p.stdout
        while True:
            size = 0
            while True:
                line = f.readline()
                if not line:
                    return
                if not line.strip():
                    break
                if line.lower().startswith(b"content-length:"):
                    size = int(line.split(b":")[1])
            try:
                self.q.put(json.loads(f.read(size)))
            except ValueError:
                pass

    def send(self, msg):
        body = json.dumps(dict(msg, jsonrpc="2.0")).encode()
        try:
            self.p.stdin.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
            self.p.stdin.flush()
        except OSError:
            pass

    def ask(self, method, params, deadline, clock):
        self.n += 1
        self.send({"id": self.n, "method": method, "params": params})
        return self.pump(deadline, clock, lambda m: m.get("id") == self.n and "method" not in m)

    def pump(self, deadline, clock, done):
        """Read messages until done(message) holds (its result) or the deadline passes (TimeoutError)."""
        while clock() < deadline:
            try:
                m = self.q.get(timeout=0.05)
            except queue.Empty:
                continue
            if m.get("method") == "textDocument/publishDiagnostics":
                self.checked.add((m.get("params") or {}).get("uri"))
            if "method" in m and "id" in m:          # the server asks: configuration gets one empty answer per item
                items = (m.get("params") or {}).get("items")
                self.send({"id": m["id"], "result": [None] * len(items) if m["method"] == "workspace/configuration" and items else None})
            if done(m):
                if "error" in m:
                    raise OSError(m["error"].get("message", "error"))
                return m.get("result")
        raise TimeoutError

    def stop(self):
        self.p.kill()
        self.p.wait()


def lsp_refs(W, defs, text, servers, clock, limit=LSP_LIMIT):
    """({index of a definition: {(file, line)}} of the references the language servers find, the lines to print)."""
    refs, notes, deadline = {}, [], clock() + limit
    root = os.path.realpath(W)
    uri = lambda f: "file://" + urllib.parse.quote(os.path.join(root, f))
    groups = {}
    for i, dd in enumerate(defs):
        lang = dd.get("language", "")
        key = "python" if lang in PY else "js" if lang in LSP_IDS else lang
        argv = servers.get(key)
        if argv and shutil.which(argv[0]):
            groups.setdefault(key, []).append(i)
        elif "no language server for %s: LSP pass skipped" % lang not in notes:
            notes.append("no language server for %s: LSP pass skipped" % lang)
    for key, idx in groups.items():
        server = Lsp(servers[key], root)
        options = {}
        tsc = shutil.which("tsc")                    # typescript-language-server needs a TypeScript: the global one
        if key == "js" and tsc and not os.path.isdir(os.path.join(root, "node_modules", "typescript")):
            options = {"tsserver": {"path": os.path.join(os.path.dirname(os.path.realpath(tsc)), "..", "lib", "tsserver.js")}}
        try:
            server.ask("initialize", {"processId": os.getpid(), "rootUri": uri("").rstrip("/"), "capabilities": {},
                                      "initializationOptions": options,
                                      "workspaceFolders": [{"uri": uri("").rstrip("/"), "name": "W"}]}, deadline, clock)
            server.send({"method": "initialized", "params": {}})
            for i in idx:
                dd = defs[i]
                src = text(dd["filePath"])
                line = (src.splitlines() or [""])[dd["startLine"] - 1] if dd["startLine"] <= len(src.splitlines()) else ""
                at = re.search(r"\b%s\b" % re.escape(dd["name"]), line)
                server.send({"method": "textDocument/didOpen", "params": {"textDocument": {
                    "uri": uri(dd["filePath"]), "languageId": LSP_IDS.get(dd.get("language"), "python"), "version": 1, "text": src}}})
                try:                                 # the server has read the workspace when it reports on the file
                    server.pump(min(deadline, clock() + 30), clock, lambda m: uri(dd["filePath"]) in server.checked)
                except TimeoutError:
                    if clock() >= deadline:
                        raise
                found = server.ask("textDocument/references", {
                    "textDocument": {"uri": uri(dd["filePath"])}, "context": {"includeDeclaration": False},
                    "position": {"line": dd["startLine"] - 1, "character": at.start() if at else 0}}, deadline, clock) or []
                for loc in found:
                    path = os.path.realpath(urllib.parse.unquote(urllib.parse.urlparse(loc["uri"]).path))
                    if path.startswith(root + os.sep):
                        refs.setdefault(i, set()).add((os.path.relpath(path, root), loc["range"]["start"]["line"] + 1))
        except TimeoutError:
            notes.append("LSP: timed out")
            break
        except OSError as e:
            notes.append("LSP: %s failed: %s" % (servers[key][0], str(e)[:200]))
        finally:
            server.stop()
    return refs, notes


def run(cmd, cwd):
    """stdout; on a failure also the exit code and stderr, so the output says why."""
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    except OSError as e:
        return "exit 127: %s" % e
    return p.stdout if p.returncode == 0 else "%s\nexit %d: %s" % (p.stdout, p.returncode, p.stderr.strip())


def read_file(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def main(argv=None, cg=None, git=None, read=read_file, servers=SERVERS, clock=time.monotonic):
    """cg(args) and git(args) run `codegraph ARGS` and `git ARGS` in W and return stdout; read(path) returns a file;
    servers names the language servers, clock the time the LSP pass reads."""
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
    status = cg(["status", W])
    named = re.search(r"Project: (.+)", status)
    index = "no index" if not named or "Not initialized" in status else named.group(1).strip()
    if os.path.realpath(index) != os.path.realpath(W):    # a folder inside another checkout reads that one's index
        print("codegraph: no index of its own in %s: `codegraph status` names %s; run `codegraph init -y \"%s\"` first"
              % (W, index, W))
        return 1
    said = [l.strip("│●└┌◇◆ ") for l in cg(["sync", W]).splitlines()]
    said = [l for l in said if l and l not in ("Syncing CodeGraph", "Done", "Scanning files...")]
    print("codegraph sync: %s" % (said[-1] if said else "no output (is codegraph on PATH?)"))
    try:
        found = json.loads(cg(["callers", "-p", W, "-j", "-l", "2000"] + (["-f", a.file] if a.file else []) + [a.name]) or "{}")
    except json.JSONDecodeError:
        found = {}
    if found.get("filteredOut"):
        print("codegraph: %s" % found.get("note", "-f %s matches no definition: showing all of them" % a.file))
    defs = found.get("definitions") or []
    if not defs:
        print("codegraph: no definition named %s in %s (check the name, the index: codegraph status \"%s\")" % (a.name, W, W))
        return 0
    try:
        indexed = [(f["path"], f.get("language", "")) for f in json.loads(cg(["files", "-p", W, "-j"]) or "[]")]
    except json.JSONDecodeError:
        indexed = []
    texts, imports, scans, binds, warned = {}, {}, {}, {}, set()

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

    def bound(f, lang):
        if f not in binds:
            binds[f] = aliases(text(f), lang)
        return binds[f]

    def scan(f, lang):                      # (word lines, def spans) of a file, once for every definition
        if f not in scans:
            scans[f] = (word_lines(text(f), lang, word), def_spans(text(f)) if lang in PY else [])
        return scans[f]

    word = a.name.rsplit(".", 1)[-1]           # Class.method: codegraph takes it whole, the code has the method word
    n = re.escape(word)
    blocks = []
    for d in defs:
        dd = d["definition"]
        home, lang = dd["filePath"], dd.get("language", "")
        head = ["\ndefinition  %s:%s  %s %s" % (home, dd["startLine"], dd.get("kind", ""), dd["name"])]
        family = PY if lang in PY else JS if lang in JS else {lang}
        if not family & (PY | JS) and lang not in warned:
            warned.add(lang)
            head.append("warning: no import filter for %s: searched every indexed %s file" % (lang, lang))
        # its module, and its package: `from pkg import name` reaches a name pkg/__init__ re-exports
        mod, pkg = module_of(home), os.path.basename(os.path.dirname(home))
        mods = {mod, pkg} - {""}
        wanted = {"mod:" + mod, "name:" + mod, "imp:" + pkg, "from:%s:%s" % (pkg, word)}
        # a method is called on an object, whose file seldom imports the class's module: no import filter
        files = [f for f, l in indexed if l in family and (f == home or a.all or not family & (PY | JS)
                                                            or dd.get("kind") == "method"
                                                            or wanted & names(f, l))]
        langs = dict(indexed)
        who_cg = {c["id"]: c for c in d.get("callers") or []}
        edges = {}   # (file, line) -> (caller name, a guess?)
        for e in d.get("edges") or []:
            c, m = who_cg.get(e.get("source"), {}), e.get("metadata") or {}
            if c:
                edges[(c["filePath"], e.get("line") or c.get("startLine"))] = (
                    c["name"], m.get("confidence") == 0.4 and m.get("resolvedBy") == "exact-match")
        # D19: the def (its start line) of each codegraph caller; module code keeps the exact-line rule
        held = {(c["filePath"], c.get("startLine")) for c in who_cg.values() if c.get("kind") != "file"}
        rows, matched = [], set()
        for f in files:
            body = text(f).splitlines()
            hits, spans = scan(f, langs.get(f))
            for ln, receivers in hits.items():
                line = body[ln - 1].strip() if ln <= len(body) else ""
                if dd.get("kind") != "method" and family & (PY | JS) and not a.all and all(
                        r is not None and r not in mods and bound(f, langs.get(f)).get(r) not in mods for r in receivers):
                    continue                       # D20: only `X.NAME` on another object: not this function
                if (f == home and ln == dd["startLine"]) or re.search(r"\b(def|function)\s*\*?\s*%s\b" % n, line):
                    continue                       # this definition, or a namesake's
                if (f, ln) in edges:
                    matched.add((f, ln))
                    who, guess = edges[(f, ln)]
                    rows.append(("cg guess" if guess else "both", f, ln, who, line[:110]))
                elif langs.get(f) in PY and (f, max([s[0] for s in spans if s[0] <= ln <= s[1]] or [None])) in held:
                    rows.append(("both", f, ln, enclosing(spans, ln), line[:110]))   # another call in a listed caller
                else:
                    rows.append(("grep only", f, ln, enclosing(spans, ln) if spans else "-", line[:110]))
        for (f, ln), (who, guess) in edges.items():
            if (f, ln) not in matched:
                rows.append(("cg guess" if guess else "cg only", f, ln or 0, who, ""))
        blocks.append((head, rows, len({(c["filePath"], c["name"]) for c in who_cg.values()})))
    refs, notes = lsp_refs(W, [d["definition"] for d in defs], text, servers, clock)
    for i, (head, rows, callers) in enumerate(blocks):
        seen = {(r[1], r[2]) for r in rows}
        rows = [("lsp",) + r[1:] if r[0] == "grep only" and (r[1], r[2]) in refs.get(i, ()) else r for r in rows]
        home = defs[i]["definition"]
        for f, ln in sorted(refs.get(i, set()) - seen - {(home["filePath"], home["startLine"])}):
            body = text(f).splitlines()
            spans = def_spans(text(f)) if f.endswith(".py") else []
            rows.append(("lsp", f, ln, enclosing(spans, ln) if spans else "-", body[ln - 1].strip()[:110] if ln <= len(body) else ""))
        print("\n".join(head))
        rows.sort(key=lambda r: (r[0] != "grep only", r[1].startswith("tests/"), r[1], r[2]))
        for mark, f, ln, who, line in rows:
            print("[%-9s] %s:%s  %s  %s" % (mark, f, ln, who, line))
        g = [r for r in rows if r[0] == "grep only"]
        print("%d codegraph callers; %d grep-only lines (%d outside tests): read each before you trust a count."
              % (callers, len(g), sum(not r[1].startswith("tests/") for r in g)))
    for note in notes:
        print(note)
    return 0


FAKE_LSP = r"""
import json, sys
def read():
    size = 0
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            sys.exit(0)
        if not line.strip():
            break
        if line.lower().startswith(b"content-length:"):
            size = int(line.split(b":")[1])
    return json.loads(sys.stdin.buffer.read(size))
def send(m):
    body = json.dumps(dict(m, jsonrpc="2.0")).encode()
    sys.stdout.buffer.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
    sys.stdout.buffer.flush()
root = ""
while True:
    m = read()
    if m.get("method") == "initialize":
        root = m["params"]["rootUri"]
        send({"id": 0, "method": "workspace/configuration", "params": {"items": [{}]}})   # a request back, as pyright sends
        send({"id": m["id"], "result": {"capabilities": {}}})
    elif m.get("method") == "textDocument/didOpen":
        send({"method": "textDocument/publishDiagnostics", "params": {"uri": m["params"]["textDocument"]["uri"], "diagnostics": []}})
    elif m.get("method") == "textDocument/references":
        send({"id": m["id"], "result": [{"uri": root + "/" + f, "range": {"start": {"line": n - 1, "character": 4},
              "end": {"line": n - 1, "character": 10}}} for f, n in json.loads(sys.argv[1])]})
    elif m.get("method") == "shutdown":
        send({"id": m["id"], "result": None})
"""


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
                   "    return helper()\n\ndef go2():\n    return helper()\n\ndef go4():\n    helper()\n    return helper()\n"
                   "import lib.util as CS\ndef go5(obj):\n    obj.helper()\n    return CS.helper()\n"),
        "other.py": "def elsewhere():\n    return helper()\n",
        "web/api.ts": "export function fetchIt() {}\n",
        "web/page.ts": ("import { fetchIt } from './api'\n// fetchIt in a comment\nconst s = 'fetchIt';\nfetchIt();\n"
                        "function x() { fetchIt(); }\nconst t = `a ${fetchIt()} b`;\n"),
        "web/stray.ts": "fetchIt();\n",
        "web/star.ts": "import * as api from './api'\napi.fetchIt();\nobj.fetchIt();\n",
        "web/own.ts": "import { fetchIt as f } from './api'\nexport function fetchIt() {}\n",
        "svc/serve.go": "package svc\n\nfunc Serve() {}\n",
        "lib/eng.py": "class Engine:\n    def ack(self):\n        return 1\n\nclass Other:\n    def ack(self):\n        return 2\n",
        "user.py": "def go3(e):\n    return e.ack()\n",
        "pkg/__init__.py": "from .util import helper2\n",
        "pkg/util.py": "def helper2():\n    return 1\n",
        "routes.py": "from pkg import helper2\nROUTES = [(\"GET\", helper2)]\nf = getattr(pkg, 'helper2', None)\n",
        "pkg/other.py": "def other():\n    return 0\n",
        "uses_pkg.py": "from pkg import other\ndef z(helper2):\n    return helper2()\n",
        "lazy.py": "import importlib\nm = importlib.import_module(\"pkg.util\")\nm.helper2()\n",
        "svc/main.go": "package svc\n\nfunc main() { Serve() }\n",
    }
    lang = {".py": "python", ".ts": "typescript", ".go": "go"}
    d_ = lambda f, n, line, lg, kind="function": {"name": n, "kind": kind, "filePath": f, "startLine": line, "id": "def:" + f, "language": lg}
    edge = lambda f, who, line, conf=0.9, start=1: ({"id": "c:%s:%s" % (f, who), "name": who, "kind": "function", "filePath": f,
                                                     "startLine": start},
                                           {"source": "c:%s:%s" % (f, who), "line": line,
                                            "metadata": {"confidence": conf, "resolvedBy": "exact-match"}})
    defs = {"helper": [(d_("lib/util.py", "helper", 1, "python"), [edge("app.py", "go", 6), edge("app.py", "go2", 9, 0.4), edge("app.py", "go4", 12, 0.9, 11)]),
                       (d_("lib/more.py", "helper", 1, "python"), [])],
            "fetchIt": [(d_("web/api.ts", "fetchIt", 1, "typescript"), [edge("web/page.ts", "x", 5)])],
            "Serve": [(d_("svc/serve.go", "Serve", 3, "go"), [])],
            "Engine.ack": [(d_("lib/eng.py", "ack", 2, "python", "method"), [])],
            "helper2": [(d_("pkg/util.py", "helper2", 1, "python"),       # N1: a file caller on the import line only
                         [({"id": "file:routes.py", "name": "routes.py", "kind": "file", "filePath": "routes.py", "startLine": 1},
                           {"source": "file:routes.py", "line": 1, "metadata": {"confidence": 0.85, "resolvedBy": "import"}})])],
            "ack": [(d_("lib/eng.py", "ack", 2, "python", "method"), []), (d_("lib/eng.py", "ack", 6, "python", "method"), [])]}
    calls, project = [], {}

    def fake_cg(args):
        calls.append(args[0])
        if args[0] == "status":
            return "CodeGraph Status\n\nProject: %s\n" % project.get("is", args[1])
        if args[0] == "sync":
            return "┌  Syncing CodeGraph\n│\n●  Already up to date\n│\n└  Done\n"
        if args[0] == "files":
            return json.dumps([{"path": f, "language": lang[os.path.splitext(f)[1]]} for f in files])
        name, only = args[-1], (args[args.index("-f") + 1] if "-f" in args else None)
        out = [{"definition": dd, "callers": [c for c, e in es], "edges": [e for c, e in es]}
               for dd, es in defs.get(name, []) if not only or dd["filePath"].endswith(only)]
        if only and not out:                # codegraph's answer when -f matches no definition
            return json.dumps({"definitions": json.loads(fake_cg(args[:-3] + args[-1:]))["definitions"], "filteredOut": True,
                               "note": 'no definition of "%s" matches file "%s" — showing all definitions instead.' % (name, only)})
        return json.dumps({"definitions": out})

    with tempfile.TemporaryDirectory() as W:
        for f, body in files.items():
            os.makedirs(os.path.dirname(os.path.join(W, f)), exist_ok=True)
            with open(os.path.join(W, f), "w") as fh:
                fh.write(body)
        subprocess.run(["git", "init", "-q"], cwd=W, check=True)

        lsp = {}                                                 # the language servers on "PATH"

        def out(*argv, git=None, clock=None):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                main(list(argv), cg=fake_cg, git=git, servers=lsp, clock=clock or time.monotonic)
            return buf.getvalue()

        o = out("helper", "-p", W)
        lines = o.splitlines()
        assert lines[0] == "codegraph sync: Already up to date", lines[:2]    # the sync result comes first
        assert calls[:2] == ["status", "sync"], calls
        assert sum(l.startswith("definition") for l in lines) == 2, o                      # one block per definition
        assert "[both     ] app.py:6  go  return helper()" in lines, o                     # an importer's call
        assert "[cg guess ] app.py:9  go2  return helper()" in lines, o                    # a 0.4 exact-match edge
        assert "[both     ] app.py:13  go4  return helper()" in lines, o                   # D19: a 2nd call in a listed caller
        assert "app.py:16" not in o and "[grep only] app.py:17  go5  return CS.helper()" in lines, o   # D20: receivers
        assert "other.py" not in o, o                                                      # no import: not shown
        assert "app.py:4" not in o and "app.py:5" not in o, o                              # comment and string
        assert o.count("codegraph callers;") == 2, o                                       # a count line per block
        o = out("helper", "-p", W, "-f", "lib/more.py")
        assert sum(l.startswith("definition") for l in o.splitlines()) == 1 and "lib/more.py" in o, o
        o = out("helper", "-p", W, "-f", "nosuch.py")
        assert o.splitlines()[1] == 'codegraph: no definition of "helper" matches file "nosuch.py" — showing all definitions instead.', o  # F7
        project["is"] = "/elsewhere/main"                                                  # F8: another checkout's index
        calls.clear()
        o = out("helper", "-p", W)
        assert "sync" not in calls and "definition" not in o, (calls, o)
        assert o.splitlines()[0].startswith("codegraph: no index of its own in %s: `codegraph status` names /elsewhere/main" % W), o
        project.clear()
        assert "exit 3: it broke" in run(["sh", "-c", "echo it broke >&2; exit 3"], W)      # F8: a failed command says why
        o = out("fetchIt", "-p", W)
        lines = o.splitlines()
        assert "[grep only] web/page.ts:4  -  fetchIt();" in lines, o                      # a JS call CodeGraph misses
        assert "[both     ] web/page.ts:5  x  function x() { fetchIt(); }" in lines, o
        assert any(l.startswith("[grep only] web/page.ts:6") for l in lines), o            # code inside ${...}
        assert "page.ts:2" not in o and "page.ts:3" not in o and "stray.ts" not in o, o
        assert "own.ts:2" not in o, o
        assert "[grep only] web/star.ts:2" in o and "star.ts:3" not in o, o                # D20: JS receivers                                                      # a namesake's definition
        o = out("Serve", git=lambda args: W)                                               # W from git
        assert "warning: no import filter for go: searched every indexed go file" in o, o
        assert "[grep only] svc/main.go:3" in o, o
        o = out("ack", "-p", W)
        assert o.count("[grep only] user.py:2  go3  return e.ack()") == 2, o              # F1: a method's caller needs no import
        o = out("Engine.ack", "-p", W)
        assert "[grep only] user.py:2  go3  return e.ack()" in o and "lib/eng.py:6" not in o, o   # F9: Class.method
        o = out("helper2", "-p", W)
        assert "[grep only] routes.py:3  -  f = getattr(pkg, 'helper2', None)" in o, o   # F3: getattr with a string
        assert "uses_pkg.py" not in o, o                                                   # another name from the package
        assert "[grep only] routes.py:2  -  ROUTES" in o and "[grep only] lazy.py:3  -  m.helper2()" in o, o   # F2: via the package
        # T-2: the LSP pass, with a fake server that speaks the protocol over stdio
        assert out("helper", "-p", W).rstrip().endswith("no language server for python: LSP pass skipped")
        lsp["python"] = [sys.executable, "-c", FAKE_LSP, json.dumps([["app.py", 6], ["other.py", 2], ["app.py", 17]])]
        o = out("helper", "-p", W, "-f", "lib/util.py")
        lines = o.splitlines()
        assert "[both     ] app.py:6  go  return helper()" in lines, o                     # a CodeGraph edge stays
        assert "[lsp      ] other.py:2  elsewhere  return helper()" in lines, o            # a reference nobody else found
        assert "[lsp      ] app.py:17  go5  return CS.helper()" in lines, o                # a grep line the server confirms
        assert "LSP pass skipped" not in o and "timed out" not in o, o
        lsp["python"] = [sys.executable, "-c", "import time; time.sleep(30)"]           # a server that never answers
        ticks = iter(range(0, 10 ** 6, 31))                                              # each look at the clock: 31 s
        o = out("helper", "-p", W, "-f", "lib/util.py", clock=lambda: next(ticks))
        assert o.rstrip().endswith("LSP: timed out") and "[both     ] app.py:6  go" in o, o
    assert code_only("a('x // y') // z\n/* q\n */ b(\"c\")") == "a('      ')     \n    \n    b(\" \")"
    print("cgcallers selftest ok")
    return 0

if __name__ == "__main__":
    sys.exit(main())
