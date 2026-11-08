#!/usr/bin/env python3
"""callcheck: run cgcallers on every function or method a diff removes, renames or gives a new signature.

    python3 -I callcheck.py [-p W] --cached          the staged diff (before a commit)
    python3 -I callcheck.py [-p W] <base>..<head>    a commit range (the controller, at each stop)
    python3 -I callcheck.py --selftest

It compares the definitions of each changed file in Python, JS/TS, Swift, Go, Rust, Java, Kotlin, Ruby, PHP, C# or
C/C++ on both sides of the diff (Python by its AST, JS/TS by a pattern for `function f(`, `f = (...) =>` and a method
`f(...) {`, the others by a generic pattern). For each name it prints the cgcallers block of that file's definition;
for a name no definition holds any more (removed, renamed) it prints the word hits cgcallers' search finds in the
tracked files of that language. The count line counts the names checked and the caller lines to read. After it, a diff
with any other code file prints a "language not covered" line that names those files.
"""
import ast
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cgcallers  # noqa: E402  (the word search and the marks are cgcallers' own)
from tickets import CODE, JS  # noqa: E402  (the one list of code file types)

PY = (".py",)
# shortcut: a JS/TS signature is read from one line; a parameter list over several lines is not compared
JS_DEF = [re.compile(p, re.M) for p in (
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*(\w+)\s*(?:<[^>]*>)?\s*\(([^)]*)\)",
    r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:function\b[^(]*)?\(([^)]*)\)",
    r"^[ \t]+(?:(?:public|private|protected|static|async|override|readonly)\s+)*(\w+)\s*(?:<[^>]*>)?\s*\(([^()]*)\)\s*(?::\s*[^{;]+)?\{")]
NOT_NAMES = {"if", "for", "while", "switch", "catch", "function", "return", "constructor", "with"}
# a statement's keyword in this file type, which cannot be a function's name there; elsewhere the same word can
NOT_NAMES_IN = {".cs": {"lock", "fixed", "using", "foreach"}, ".java": {"synchronized"}, ".php": {"use", "foreach"}}
# shortcut: a generic pattern, not a parser: of two overloads only the first is compared, a parenthesis nested two deep ends
# the match, a function a macro makes is not seen, a return type's change is not compared, a Swift `init`'s callers write the
# type's name, so its word search finds none, and a prose line or a C++ or Java local variable (`Widget w(parent);`) that
# reads like a declaration can give a false name; use a language's parser when a project's stops miss real names.
PARAMS = r"\s*\(((?:[^()]|\([^()]*\))*)\)"
WORDS = r"^[ \t]*(?:[\w@()\"]+[ \t]+)*?"
KEYWORD_DEF = re.compile(WORDS + r"(?:func|fn|fun|function)[ \t]+(?:\([^)]*\)\s*)?(?:<[^>]*>\s*)?(?:[\w<>?,]+\.)?&?(\w+)\s*(?:<[^(]*>)?" + PARAMS, re.M)
SWIFT_INIT = re.compile(r"^[ \t]*(?:[\w@()]+[ \t]+)*?(init)[?!]?\s*(?:<[^(]*>)?" + PARAMS, re.M)
RUBY_DEF = re.compile(r"^[ \t]*(?:\w+[ \t]+)*?def[ \t]+(?:self\.)?(\w+[?!=]?)[ \t]*\(?((?<=\()[^)\n#]*|[^)\n;#=]*)", re.M)
TYPED_DEF = re.compile(r"^[ \t]*(?!(?:return|new|throw|else|case|await|yield|delete|goto|assert|do|in|using|typedef|co_return|co_await|co_yield)\b)"
                       r"(?:[\w\[@](?:[\w:<>,\[\].?~]|[*&]+(?=[>,]))*[ \t*&]+)+(?:\w+::)*(~?\w+)" + PARAMS
                       + r"\s*(?:const\b\s*|noexcept\b\s*|override\b\s*|final\b\s*)*(?:throws\s+[\w., ]+)?\s*(?:\{|=>|:|;|$)", re.M)
C_FAMILY = (".c", ".h", ".cc", ".cpp", ".hpp")
JVM_FAMILY = (".java", ".kt", ".kts")
OTHER_DEF = {".swift": (KEYWORD_DEF, SWIFT_INIT), ".go": (KEYWORD_DEF,), ".rs": (KEYWORD_DEF,), ".kt": (KEYWORD_DEF,), ".kts": (KEYWORD_DEF,),
             ".php": (KEYWORD_DEF,), ".rb": (RUBY_DEF,),
             **{e: (TYPED_DEF, JS_DEF[2]) for e in (".java", ".cs") + C_FAMILY}}
COMPARED = PY + JS + tuple(OTHER_DEF)


def git(W, *args, missing_ok=False):
    """git's stdout; a failure stops with git's own words (missing_ok: a path absent on one side gives "")."""
    p = subprocess.run(["git", "-C", W] + list(args), capture_output=True, text=True, errors="surrogateescape")   # -z: a name's raw bytes
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
    suffix = os.path.splitext(path)[1]
    for rx in OTHER_DEF.get(suffix, JS_DEF):
        for m in rx.finditer(src):
            if m.group(1) not in NOT_NAMES | NOT_NAMES_IN.get(suffix, set()):
                out.setdefault(m.group(1), "(%s)" % " ".join(m.group(2).split()))
    return out


def changes(W, spec):
    """([(kind, name, file, note)] for each removed, renamed or re-signed function in the diff, [the code files of the
    diff in a language not compared])."""
    cached = spec == "--cached"
    base, head = ("HEAD", "") if cached else spec.split("..", 1)
    diff = git(W, "diff", "-z", "--name-status", "-M", *(["--cached"] if cached else [base, head])).split("\0")[:-1]   # -z: no quoted names
    out, other = [], []
    while diff:
        status, old = diff.pop(0), diff.pop(0)
        new = diff.pop(0) if status[0] in "RC" else old
        if not old.endswith(COMPARED) and os.path.splitext(new)[1] in CODE and not new.endswith(COMPARED):
            other.append(new)
        if not old.endswith(COMPARED) or status.startswith("A"):
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
    return out, other


def run_cgcallers(W, name, path, script=os.path.join(HERE, "cgcallers.py")):
    p = subprocess.run([sys.executable, "-I", script, name, "-p", W, "-f", path], capture_output=True, text=True)
    return p.stdout + ("\n[cgcallers failed] exit %d: %s" % (p.returncode, p.stderr.strip()[-500:]) if p.returncode else "")


def word_hits(W, name, path):
    """The code lines that still name a function no definition holds, by cgcallers' own rules: the word search in
    its file and the files that import its module (any file for a method), with no namesake's def line."""
    suffix = os.path.splitext(path)[1]
    word, ext = name.rsplit(".", 1)[-1], next((g for g in (PY, JS, C_FAMILY, JVM_FAMILY) if suffix in g), (suffix,))
    lang = "python" if ext == PY else "typescript" if ext == JS else suffix
    mod, pkg = cgcallers.module_of(path), os.path.basename(os.path.dirname(path))
    wanted = {"mod:" + mod, "name:" + mod, "imp:" + pkg, "from:%s:%s" % (pkg, word)}
    method = "." in name
    rows = []
    for f in git(W, "ls-files", "-z").split("\0"):
        if f.endswith(ext):
            try:
                src = cgcallers.read_file(os.path.join(W, f))
            except OSError:
                continue
            if f != path and not method and ext in (PY, JS) and not wanted & cgcallers.imported(src, lang):
                continue
            body = src.splitlines()
            for ln in cgcallers.word_lines(src, lang, word):
                line = body[ln - 1].strip()
                if not re.search(r"\b(def|function|func|fun|fn)\s*\*?\s*%s\b" % re.escape(word), line):
                    rows.append("[grep only] %s:%d  %s" % (f, ln, line[:110]))
    return rows


def check(W, spec, callers=run_cgcallers):
    found, other = changes(W, spec)
    lines = []
    for kind, name, path, note in found:
        lines.append("\n== %s: %s (%s)%s" % (kind, name, path, " " + note if note else ""))
        text = callers(W, name, path)
        if kind != "signature" and ("no definition named" in text or "matches file" in text):   # none left in this file
            text += "\n".join(["word search (no definition holds %s any more):" % name] + word_hits(W, name, path))
        lines.append(text.rstrip())
    to_read = sum(l.startswith("[") for t in lines for l in t.splitlines())
    lines.append("\ncallcheck: %d names checked (removed, renamed or re-signed), %d caller lines to read" % (len(found), to_read))
    if other:
        lines.append("callcheck: language not covered, not compared: %s; run cgcallers by hand on what they remove or re-sign" % ", ".join(other))
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
    selftest_languages()
    print("callcheck selftest ok")
    return 0


def selftest_languages():
    """Other languages, the not-covered line and the JS method read, on a scratch repo with a fake cgcallers."""
    import tempfile
    # every keyword form a body holds: a name from one of them shows up as a removed name
    body = ("    if (a) {\n    for (a) {\n    switch (a) {\n    catch (a) {\n    while (a) {\n    return other(a);\n"
            "    return other(a)\n    else if (a) {\n    } else if (a) {\n    } catch (a) {\n    throw new Oops(a);\n"
            "    new Thing(a) {\n    other(a);\n    other(a)\n    let x = other(a);\n    // int notReal(int a) {\n")
    gone = {"g.go": ("func goneGo(a int) int {\n%s}\nfunc (s *Srv) goneMethod(b int) {\n}\n" % body, "goneGo goneMethod"),
            "r.rs": ("pub(crate) async fn gone_rust<T>(a: T) -> i32 {\n%s}\n" % body, "gone_rust"),
            "J.java": ("class J {\n  public static int goneJava(int a) throws Oops {\n%s  }\n}\n" % body, "goneJava"),
            "k.kt": ("suspend fun <T> String.goneKotlin(a: T): Int {\n%s}\n" % body, "goneKotlin"),
            "o.rb": ("class O\n  def self.gone_ruby?(a, b)\n    if (a)\n    end\n    return other(a)\n    while (a)\n    end\n  end\n"
                     "  def gone_bare\n  end\nend\n", "gone_ruby? gone_bare"),
            "p.php": ("<?php\nclass P {\n  public static function gonePhp($a) {\n%s  }\n}\n" % body, "gonePhp"),
            "c.cs": ("class C {\n  public async Task<int> GoneSharp(int a)\n  {\n%s  }\n}\n" % body, "GoneSharp"),
            "v.cpp": ("std::vector<int> Klass::gone_cpp(int a) const {\n%s}\nstatic int gone_c(void)\n{\n}\n" % body, "gone_cpp gone_c")}
    swift = {"s.swift": ("class S {\n  init(name: String) {\n    self.init(a: 1)\n  }\n  func oldHelper(a: Int) -> Int {\n%s  }\n"
                         "  public func goodbye(to who: String, cb: () -> Void) -> String { who }\n"
                         "  private static func same<T>(\n    a: T\n  ) {\n  }\n}\n" % body,
                         "class S {\n  init(name: String, age: Int) {\n  }\n  public func goodbye(to who: String, cb: (Int) -> Void, loud: Bool) -> String { who }\n"
                         "  private static func same<T>(\n    a: T\n  ) {\n  }\n}\n")}
    js = {"w.js": ("describe('a', function () {\n  describe('b', function () {\n  })\n})\nclass W {\n  realMethod(x) {\n    return x\n  }\n}\n",
                   "class W {\n}\n")}

    def names(before, after, spec="HEAD~1..HEAD"):
        """(the names, the output) of a commit that turns `before` into `after`, each {file: text}; a None text deletes.
        With spec --cached the second change is staged, not committed."""
        with tempfile.TemporaryDirectory() as W:
            g = lambda *a: subprocess.run(["git", "-C", W] + list(a), check=True, capture_output=True)
            g("init", "-q"), g("config", "user.name", "t"), g("config", "user.email", "t@example.com")
            def put(files, commit=True):
                for f, body_ in files.items():
                    if body_ is None:
                        os.remove(os.path.join(W, f))
                    else:
                        with open(os.path.join(W, f), "w") as fh:
                            fh.write(body_)
                g("add", "-A")
                if commit:
                    g("commit", "-qm", "x", "--allow-empty")
            put(before)
            put(after, spec != "--cached")
            asked = []
            fake = lambda W_, name, path: asked.append(name) or "definition  %s:1  function %s" % (path, name)
            out = check(W, spec, fake)
            return asked, out

    asked, out = names({f: s[0] for f, s in swift.items()}, {f: s[1] for f, s in swift.items()})
    assert sorted(asked) == ["goodbye", "init", "oldHelper"], (asked, out)
    assert "== removed: oldHelper (s.swift)" in out and "== signature: init (s.swift) (name: String) -> (name: String, age: Int)" in out, out
    assert "== signature: goodbye (s.swift)" in out and out.splitlines()[-1].startswith("callcheck: 3 names checked"), out
    for f, (src, want) in gone.items():
        asked, out = names({f: src}, {f: "\n"})
        assert sorted(asked) == sorted(want.split()), (f, asked, out)
    asked, out = names({f: s[0] for f, s in js.items()}, {f: s[1] for f, s in js.items()})
    assert asked == ["realMethod"], (asked, out)                           # R12: describe('a', function () { is no method
    sw = {f: s[0] for f, s in swift.items()}
    words = "callcheck: language not covered, not compared: %s; run cgcallers by hand on what they remove or re-sign"
    asked, out = names(dict(sw, **{"run.sh": "a\n", "a.vue": "a\n", "n.md": "a\n", "d.xyz": "a\n", "z.py": "x = 1\n"}),
                       {"s.swift": swift["s.swift"][1], "run.sh": "b\n", "n.md": "b\n", "d.xyz": "b\n", "z.py": "x = 2\n", "a.vue": None})
    lines = out.splitlines()
    assert lines[-2].startswith("callcheck: 3 names checked") and lines[-1] == words % "a.vue, run.sh", out
    asked, out = names({"n.md": "a\n"}, {"n.md": "b\n"})
    assert asked == [] and out == "\ncallcheck: 0 names checked (removed, renamed or re-signed), 0 caller lines to read", out
    asked, out = names({"z.py": "def f():\n    return 1\n"}, {"z.py": "x = 1\n"})
    assert "not covered" not in out and asked == ["f"], out
    asked, out = names({"o.m": "a\n"}, {"o.m": "b\n"})                       # a code type no pattern covers is named
    assert asked == [] and out.splitlines()[-1] == words % "o.m", out
    asked, out = names({"p.hpp": "int gone_hpp(int a) {\n}\n", "s.kts": "fun goneKts(a: Int) {\n}\n"}, {"p.hpp": "\n", "s.kts": "\n"})
    assert sorted(asked) == ["goneKts", "gone_hpp"] and "not covered" not in out, out
    asked, out = names({"new.sh": "a\n"}, {"new2.sh": "a\n"})               # a new code file: nothing compared, so named
    assert out.splitlines()[-1] == words % "new2.sh", out
    # F22: a file name git would quote is compared or named, in a range and staged, also through a rename
    for spec in ("HEAD~1..HEAD", "--cached"):
        asked, out = names({"R\u00e9sum\u00e9.swift": "func goneU(a: Int) {\n}\n", "stuff \u00e9.sh": "a\n"},
                           {"R\u00e9sum\u00e9.swift": "\n", "stuff \u00e9.sh": "b\n"}, spec)
        assert asked == ["goneU"] and out.splitlines()[-1] == words % "stuff \u00e9.sh", (spec, asked, out)
    long_body = "func keep(a: Int) {\n}\n" * 20
    asked, out = names({"\u00e9 old.swift": long_body + "func goneR(a: Int) {\n}\n"}, {"\u00e9 old.swift": None, "\u00e9 new.swift": long_body})
    assert asked == ["goneR"] and "\u00e9 old.swift" in out and "R100" not in out, (asked, out)
    # F23: a line of factors with no spaces ends, in a fixed input; the pointer forms stay; 10 s is only a backstop (this takes under 0.2 s)
    for path, line in (("x.cpp", "*".join("m%d" % i for i in range(40))), ("x.java", "&".join("F%d" % i for i in range(40)))):
        code = "import sys; sys.path.insert(0, %r); import callcheck; assert callcheck.defs(%r, %r) == {}" % (HERE, "  " + line + ";\n", path)
        subprocess.run([sys.executable, "-I", "-c", code], check=True, timeout=10)
    pointers = {"int* a1(int a) {": "a1", "int *a2(int a) {": "a2", "char** a3(int a) {": "a3", "const std::vector<int>& a4(int a) const {": "a4",
                "std::vector<int*> a5(int a) {": "a5", "std::map<int*, char&> a6(int a) {": "a6", "Foo * a7(int a) {": "a7", "Foo& a8(int a) {": "a8",
                "Klass::Inner* Klass::a9(int a) {": "a9"}
    for line, name in pointers.items():
        assert list(defs(line + "\n}\n", "x.cpp")) == [name], line
    # F24: words before Ruby's def; F25: a closure's `use` is no name, and a Ruby body or a comment is no signature
    rb = "private def helper(a)\nend\nmodule_function def mf(a)\nend\npublic_class_method def self.pcm(b)\nend\n# def not_real(a)\n"
    assert defs(rb, "a.rb") == {"helper": "(a)", "mf": "(a)", "pcm": "(b)"}, defs(rb, "a.rb")
    assert defs("<?php\nreturn function ($a) use ($b) {\n};\n", "c.php") == {}, defs("<?php\nreturn function ($a) use ($b) {\n};\n", "c.php")
    asked, out = names({"b.rb": "def foo; 1; end\ndef bar # note one\nend\ndef baz(a) # one\nend\n"},
                       {"b.rb": "def foo; 2; end\ndef bar # note two\nend\ndef baz(a) # two\nend\n"})
    assert asked == [], (asked, out)
    # F301: a word that is a keyword in one file type is a name in the others; each form both ways
    for path, line, name in (("a.swift", "func lock() {}", "lock"), ("a.rs", "fn lock(&self) {", "lock"), ("a.go", "func (m *M) lock() {", "lock"),
                             ("A.java", "public void lock() {", "lock"), ("a.cpp", "void lock(int a) {", "lock"), ("a.ts", "export function use(a: string) {", "use"),
                             ("a.js", "function fixed(a) {", "fixed"), ("a.kt", "fun use(a: Int) {", "use")):
        assert list(defs(line + "\n}\n", path)) == [name], (path, line)
    for path, line in (("a.cs", "  lock (x) {"), ("a.cs", "  fixed (x) {"), ("a.cs", "  using (x) {"), ("a.cs", "  foreach (x) {"), ("A.java", "  synchronized (x) {"),
                       ("a.php", "  return function ($a) use ($b) {"), ("a.php", "  foreach ($a as $b) {")):
        assert defs(line + "\n}\n", path) == {}, (path, line)
    # F306: a Ruby endless method's body is no signature; a default value in parentheses still is
    asked, out = names({"e.rb": "def foo = 1\ndef bar(a = 1) = 2\n"}, {"e.rb": "def foo = 2\ndef bar(a = 3) = 2\n"})
    assert asked == ["bar"], (asked, out)
    # F302: a file name that is not UTF-8 ends with no traceback, through the real script; the line names it, escaped
    if os.name == "posix":
        with tempfile.TemporaryDirectory() as W:
            g = lambda *a, **k: subprocess.run(["git", "-C", W] + list(a), check=True, capture_output=True, **k)
            g("init", "-q"), g("config", "user.name", "t"), g("config", "user.email", "t@example.com")
            blob = g("hash-object", "-w", "--stdin", input=b"func goneB(a: Int) {\n}\n").stdout.decode().strip()
            for raw in (b"caf\xe9.swift", b"caf\xe9.sh"):
                g("update-index", "--add", "--cacheinfo", b"100644," + blob.encode() + b"," + raw)
            g("commit", "-qm", "one")
            g("update-index", "--force-remove", b"caf\xe9.swift")
            g("update-index", "--force-remove", b"caf\xe9.sh")
            g("commit", "-qm", "two")
            p = subprocess.run([sys.executable, "-I", os.path.abspath(__file__), "-p", W, "HEAD~1..HEAD"], capture_output=True)
            said = p.stdout.decode("utf-8") + p.stderr.decode("utf-8", "replace")
            assert p.returncode == 0 and "Traceback (most recent call last):\n  File" not in p.stderr.decode("utf-8", "replace"), said
            assert "== removed: goneB" in said and "not compared: caf\\udce9.sh;" in said, said
    # the word search for a removed name covers the file type, and a namesake's def is no caller
    with tempfile.TemporaryDirectory() as W:
        g = lambda *a: subprocess.run(["git", "-C", W] + list(a), check=True, capture_output=True)
        g("init", "-q")
        for f, text in (("a.swift", "func other() {\n  oldHelper(1)\n}\n"), ("b.swift", "func oldHelper(a: Int) {\n}\n"),
                        ("c.go", "oldHelper()\n"), ("h.h", "int gone_c(int a);\n"), ("i.cpp", "gone_c(1);\n")):
            with open(os.path.join(W, f), "w") as fh:
                fh.write(text)
        g("add", "-A")
        assert word_hits(W, "oldHelper", "gone.swift") == ["[grep only] a.swift:2  oldHelper(1)"], "only Swift files; no def line"
        assert "[grep only] i.cpp:1  gone_c(1);" in word_hits(W, "gone_c", "v.c"), "a C name: the C family's files"
    # F26: the JVM family, both ways; another family's file is not searched; F22: a caller's file name git would quote
    with tempfile.TemporaryDirectory() as W:
        g = lambda *a: subprocess.run(["git", "-C", W] + list(a), check=True, capture_output=True)
        g("init", "-q")
        for f, text in (("build.kts", "goneK(1)\nJ.goneJ(2)\n"), ("use.kt", "J.goneJ(1)\ngoneK(2)\n"), ("U.java", "class U { int a = goneK(1); }\n"),
                        ("o.cpp", "goneK(1);\n"), ("\u00e9 s.swift", "goneS(1)\n")):
            with open(os.path.join(W, f), "w") as fh:
                fh.write(text)
        g("add", "-A")
        assert word_hits(W, "goneK", "k.kt") == ["[grep only] U.java:1  class U { int a = goneK(1); }", "[grep only] build.kts:1  goneK(1)", "[grep only] use.kt:2  goneK(2)"], word_hits(W, "goneK", "k.kt")
        assert word_hits(W, "goneJ", "J.java") == ["[grep only] build.kts:2  J.goneJ(2)", "[grep only] use.kt:1  J.goneJ(1)"], word_hits(W, "goneJ", "J.java")
        assert word_hits(W, "goneS", "g.swift") == ["[grep only] \u00e9 s.swift:1  goneS(1)"], word_hits(W, "goneS", "g.swift")


def main(argv):
    if argv[1:] == ["--selftest"]:
        return selftest()
    args = argv[1:]
    W = args[args.index("-p") + 1] if "-p" in args else git(os.getcwd(), "rev-parse", "--show-toplevel").strip()
    spec = [a for i, a in enumerate(args) if a != "-p" and (i == 0 or args[i - 1] != "-p")]
    if len(spec) != 1 or not (spec[0] == "--cached" or ".." in spec[0]):
        sys.exit(__doc__)
    sys.stdout.reconfigure(errors="backslashreplace")   # a file name that is not UTF-8
    print(check(W, spec[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
