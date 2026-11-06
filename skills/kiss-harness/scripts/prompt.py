#!/usr/bin/env python3
"""Print one filled prompt (SKILL.md); the controller gives it to a new subagent or sends it to a running one.

  python3 -I prompt.py start R KEY=VALUE ...                 write the run's values once to R/run.json, with
                                                             VERSION (the running plugin's), and WARN for each
                                                             facts line the run needs and PROJECT lacks
  python3 -I prompt.py <implementer|reviewer|severity|fix|recheck> R [KEY=VALUE ...]
  python3 -I prompt.py --selftest

start keys: W (worktree), BR (branch), SCR (scratch folder), MAIN (the main checkout, never touched), PROJECT (the
project facts file), TITLE, BASE, SMOKE, APP. A step takes only the values that change per call: HEAD, ROUND,
FIX_BASE, FIX_HEAD, ELAPSED (a call value wins over run.json). A step reads its file by a fixed name in R: severity
review-<ROUND>.md (the reviewer's findings), fix fix-<ROUND>.md (the fix list), recheck answer-<ROUND>.md (the
implementer's answer); the sort writes sort-<ROUND>.json. Filled here: HB (the skill folder) and CLOCK (ELAPSED and
BUDGET, in seconds: "Time: elapsed 340s of a 1200s budget."; empty without ELAPSED). With ELAPSED and no BUDGET, the
budget is 10 minutes per ticket in R/tickets.json plus 2 hours for the reviews and fix rounds, plus the facts
file's `Full check time:` minutes when it has that line. A value the template
needs that neither run.json nor the call gives is an error that names it. Every call prints a line on stderr when
a newer KISS version folder sits beside the running one.
"""
import json, os, re, string, sys

HB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(HB))   # the plugin; in a plugin cache, its version folder
MANIFESTS = (".claude-plugin/plugin.json", ".codex-plugin/plugin.json", "gemini-extension.json", ".antigravity-plugin/plugin.json")
FACTS = ("Full check time:", "Smoke check", "Merge:", "After merge:", "Flake check:", "Shared test resources:")
T = os.path.join(HB, "templates")
PER_TICKET_S, REVIEW_S = 600, 7200
STEPS = ("implementer", "reviewer", "severity", "fix", "recheck")
START_KEYS = {"W", "BR", "SCR", "MAIN", "PROJECT", "TITLE", "BASE", "SMOKE", "APP"}
FILES = {"severity": ("FINDINGS", "review-{}.md"), "fix": ("FINDINGS", "fix-{}.md"), "recheck": ("ANSWER", "answer-{}.md")}


def budget(run):
    """Seconds for a run: 10 min per ticket in run/tickets.json, plus 2 h, plus the facts file's full check time."""
    with open(os.path.join(run, "tickets.json")) as f:
        s = PER_TICKET_S * len(json.load(f)) + REVIEW_S
    try:
        with open(os.path.join(run, "run.json")) as f, open(json.load(f)["PROJECT"]) as p:
            m = re.search(r"^\W*Full check time:\s*(\d+)", p.read(), re.M)
    except (OSError, KeyError, ValueError):
        m = None
    return s + 60 * int(m.group(1)) if m else s


def fill(step, keys):
    text = open(os.path.join(T, step + ".md")).read()
    keys = dict(keys)
    keys.setdefault("HB", HB)
    e, b = keys.pop("ELAPSED", None), keys.pop("BUDGET", None)
    if e is not None and b is None and "R" in keys:
        b = budget(keys["R"])
    keys["CLOCK"] = f"Time: elapsed {e}s of a {b}s budget." if e is not None and b is not None else ""
    names = set(re.findall(r"\$([A-Z_]+)", text))
    missing = sorted(names - set(keys))
    if missing:
        sys.exit(f"{step}: missing {', '.join(missing)}")
    return string.Template(text).substitute(keys)


def pairs(args):
    bad = [a for a in args if "=" not in a]
    if bad:
        sys.exit(f"not KEY=VALUE: {' '.join(bad)}")
    return dict(a.split("=", 1) for a in args)


def version_key(name):
    """A sort key for a version folder name (a prerelease ranks below its release), or None for any other name."""
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?", name)
    if not m:
        return None
    pre = [(0, int(x), "") if x.isdigit() else (1, 0, x) for x in (m.group(4) or "").split(".") if x]
    return tuple(int(x) for x in m.group(1, 2, 3)) + (not pre, pre)


def version(root):
    """The running plugin's version from the first manifest it has (all four carry the same one), or None."""
    for m in MANIFESTS:
        try:
            with open(os.path.join(root, m)) as f:
                return json.load(f)["version"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return None


def newer(root):
    """The line for stderr when a sibling of the running plugin's version folder holds a higher version (D10);
    nothing for a plugin with no manifest."""
    run = os.path.basename(root)
    if version_key(run) is None or version(root) is None:
        return ""
    vs = [v for v in os.listdir(os.path.dirname(root)) if version_key(v) and version_key(v) > version_key(run)]
    best = max(vs, key=version_key, default=None)
    return f"KISS {best} is installed; this session runs {run}: start the run in a new session" if best else ""


def start(R, values, root=ROOT):
    unknown = sorted(set(values) - START_KEYS)
    if unknown:
        sys.exit(f"start: unknown keys {', '.join(unknown)} (known: {', '.join(sorted(START_KEYS))})")
    v = version(root) or "unknown"
    with open(os.path.join(R, "run.json"), "w") as f:
        json.dump(dict(values, VERSION=v), f, indent=1)
    out = [f"wrote {os.path.join(R, 'run.json')}: {', '.join(sorted(values))}, VERSION {v}"]
    try:
        with open(values.get("PROJECT", "")) as p:
            text = p.read()
        out += [f"WARN: the facts file has no `{line}` line" for line in FACTS
                if not re.search(r"^\W*" + re.escape(line), text, re.M)]
    except OSError:
        out.append(f"WARN: no facts file at {values.get('PROJECT', '(no PROJECT)')}")
    return "\n".join(out)


def prompt(step, R, call):
    """The step's template filled from R/run.json, the call's values and the step's fixed-name file."""
    path = os.path.join(R, "run.json")
    if not os.path.isfile(path):
        sys.exit(f"no {path}: run `prompt.py start {R} KEY=VALUE ...` first")
    with open(path) as f:
        keys = dict(json.load(f), **call, R=R)
    if step in FILES:
        if "ROUND" not in keys:
            sys.exit(f"{step}: missing ROUND")
        name, pattern = FILES[step]
        p = os.path.join(R, pattern.format(keys["ROUND"]))
        if not os.path.isfile(p):
            sys.exit(f"{step}: missing {p}")
        keys[name] = open(p).read().strip()
    return fill(step, keys)


def main(argv, root=ROOT):
    if argv[1:] == ["--selftest"]:
        return selftest()
    if len(argv) < 3 or argv[1] not in ("start",) + STEPS or "=" in argv[2]:
        sys.exit(__doc__)
    step, R, values = argv[1], os.path.abspath(argv[2]), pairs(argv[3:])
    warn = newer(root)
    if warn:
        print(warn, file=sys.stderr)
    print(start(R, values, root) if step == "start" else prompt(step, R, values))


def selftest():
    import contextlib, io, tempfile

    def run(*argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main(["prompt.py", *argv])
        return buf.getvalue()

    def stops(*argv):
        try:
            run(*argv)
        except SystemExit as x:
            return str(x)
        raise AssertionError(f"must stop: {argv}")

    with tempfile.TemporaryDirectory() as R:
        with open(os.path.join(R, "tickets.json"), "w") as f:
            json.dump([{"id": f"T-{i}"} for i in range(11)], f)
        assert budget(R) == 13800, "11 tickets: 3 h 50 min"
        assert stops("implementer", R).startswith("no "), "a step before start stops"
        run("start", R, "W=/w", "BR=b", "SCR=/s", "MAIN=/m", "PROJECT=/w/.kiss/project.md", "TITLE=Run 9", "BASE=abc",
            "SMOKE=python3 tests/x.py", "APP=start it on port 1")
        assert json.load(open(os.path.join(R, "run.json")))["TITLE"] == "Run 9", "start writes run.json"
        assert "unknown keys HEAD" in stops("start", R, "HEAD=x"), "a per-call key is not a run value"
        assert stops("implementer", "W=/w") == __doc__, "the KEY=VALUE-only form is gone"
        for name, body in (("review-1.md", '{"findings": ["REVIEW-ONE"]}'), ("fix-1.md", "FIX-LIST-ONE"),
                           ("answer-1.md", "ANSWER-ONE")):
            with open(os.path.join(R, name), "w") as f:
                f.write(body)
        out = run("implementer", R, "ELAPSED=340", "BUDGET=1200")
        rv = run("reviewer", R, "HEAD=def")
        loop = {"severity": run("severity", R, "ROUND=1"), "fix": run("fix", R, "ROUND=1", "ELAPSED=5"),
                "recheck": run("recheck", R, "ROUND=1", "FIX_BASE=a1", "FIX_HEAD=b2")}
        for step, text in [("implementer", out), ("reviewer", rv)] + list(loop.items()):
            assert not re.search(r"\$[A-Z_]+", text), (step, "a $NAME is left")
            assert "Run 9" in text or step == "recheck", (step, "the title from run.json")
        assert "Time: elapsed 340s of a 1200s budget." in out and "/w/.kiss/project.md" in out
        assert "of a 13800s budget" in loop["fix"], "the budget from R/tickets.json"
        assert "REVIEW-ONE" in loop["severity"] and "FIX-LIST-ONE" in loop["fix"] and "ANSWER-ONE" in loop["recheck"]
        assert "a1..b2" in loop["recheck"] and "abc..def" in rv and "start it on port 1" in rv
        assert "HEAD" in stops("reviewer", R), "a value missing from both stops with its name"
        assert "missing ROUND" in stops("fix", R) and "review-2.md" in stops("severity", R, "ROUND=2")
        sv = loop["severity"]
        assert os.path.join(R, "sort-1.json") in sv and "End with one message" not in sv, "the sort writes a file and goes on"
        start_keys = ["W=/w", "BR=b", "SCR=/s", "MAIN=/m", "TITLE=Run 9", "BASE=abc", "SMOKE=x", "APP=y"]
        facts = os.path.join(R, "project.md")
        for body, want in (("- Full check time: 12 minutes\n", 13800 + 720), ("- The full check: make all\n", 13800)):
            with open(facts, "w") as f:
                f.write(body)
            run("start", R, "PROJECT=" + facts, *start_keys)
            assert f"of a {want}s budget" in run("implementer", R, "ELAPSED=0"), ("the facts file's full check time adds to the budget", body)
        run("start", R, "PROJECT=/w/.kiss/project.md", *start_keys)
        assert os.path.exists(os.path.join(HB, "references", "traps.md"))
        for text in (out, rv):   # every agent of a run reads the same traps
            assert HB + "/references/traps.md" in text
    assert "mattpocock-skills:tdd" in out and "Skipped:" in out and "Risk:" in out
    assert "longer than about 2 minutes goes in the background" in out and "never a sleep or poll loop" in out, "a long command runs in the background, never a poll loop"
    for rule in ("at least three kinds of bad input", "sweeps every file type", "Never relax the limit or the expected value"):
        assert out.count(rule) == 1, ("each test rule appears once", rule)
    assert "write a `Risk:` line instead" in out, "the never-relax rule names its Risk line"
    for rule in ("list in its test the forms it must still accept and refuse", "Skip tdd's refactor step and its `code-review` pointer",
                 "cannot see a script's own `--selftest`"):
        assert out.count(rule) == 1, ("the parser, refactor and affected rules each appear once", rule)
    assert "stays out of the loop" not in out and "a mod's tests" in out, "one reading of refactoring; affected's blind spot named"
    assert loop["fix"].splitlines()[0] == ("Round 1 of Run 9: these items (review findings or an owner decision), to do now. "
                                           "Time: elapsed 5s of a 13800s budget."), "an owner's decision is not read as a review finding"
    assert "cannot see a script's own `--selftest`" in loop["fix"] and "a mod's tests" in loop["fix"], "the fix round runs what affected misses"
    assert "Triage" in rv and "check that each settlement holds" in rv and "do not report a settled line again as new" in rv, "the reviewer checks settled lines, never reports them as new"
    assert 'codegraph node -p "/w" <name>` for each function the ticket changes' in out and "Never `grep" in out, "one function is read with codegraph node, never grep plus sed"
    for rule in ("codegraph node -p", "codegraph callers -p", "cgcallers.py", "codegraph sync -q", "codegraph affected",
                 "Never the full check", "by explicit path", "callcheck.py"):
        assert out.count(rule) == 1, ("each CodeGraph and commit rule appears once", rule)
    assert re.search(r'callcheck\.py" -p "/w" --cached`.*keep its output for step 6.*`## <ID> <commit>`, the callcheck output from step 5', out, re.S), "callcheck's output goes into the ticket's progress entry"
    assert "read every `[grep only]` and `[lsp]` line" in out, "cgcallers' grep-only and lsp lines are read"
    assert "ponytail:ponytail-review" in rv and "G. Risk, load and speed" in rv and "A|B|C|D|E|F|G" in rv
    assert "failed before" in loop["fix"] and '"test":' in loop["fix"], "each fix names its test"
    assert 'until the controller sends "product free"' in out and 'On "product free", run the held checks first' in out, "the hold and its end"
    six = {"Full check time:": "- Full check time: 2 minutes", "Smoke check": "- Smoke check (one fast test): `make smoke`",
           "Merge:": "- Merge: ask", "After merge:": "- After merge: ask", "Flake check:": "- Flake check: `make test` x 5",
           "Shared test resources:": "- Shared test resources: none"}
    template = open(os.path.join(T, "project.md")).read()
    assert all(re.search(r"^\W*" + re.escape(line), template, re.M) for line in FACTS), "each line start checks is in the facts template"
    with tempfile.TemporaryDirectory() as cache:                          # a scratch plugin cache: <cache>/<version>/
        def plugin(v):
            os.makedirs(os.path.join(cache, v))
            with open(os.path.join(cache, v, "gemini-extension.json"), "w") as f:
                json.dump({"version": v}, f)
            return os.path.join(cache, v)

        def call(root, *argv):
            o, e = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(o), contextlib.redirect_stderr(e):
                main(["prompt.py", *argv], root=root)
            return o.getvalue(), e.getvalue()
        root, R = plugin("2.1.1"), os.path.join(cache, "run")
        plugin("2.1.0")
        os.makedirs(os.path.join(cache, "notes"))
        os.makedirs(R)
        with open(os.path.join(R, "tickets.json"), "w") as f:
            json.dump([{"id": "T-1"}], f)
        facts = os.path.join(R, "project.md")
        for body, warned in (("# Facts\n- Build steps: none\n", list(six)), ("\n".join(six.values()) + "\n", []), (None, [facts])):
            if body is None:
                os.remove(facts)
            else:
                with open(facts, "w") as f:
                    f.write(body)
            os.remove(os.path.join(R, "run.json")) if os.path.exists(os.path.join(R, "run.json")) else None
            o, e = call(root, "start", R, "PROJECT=" + facts, *start_keys)
            warns = [l for l in o.splitlines() if l.startswith("WARN")]
            assert len(warns) == len(warned) and all(sum(w in l for l in warns) == 1 for w in warned), (body, o)
            assert json.load(open(os.path.join(R, "run.json")))["VERSION"] == "2.1.1" and e == "", (body, o, e)
        quiet = call(root, "implementer", R, "ELAPSED=1")
        assert quiet[1] == "" and "Run 9" in quiet[0], "an older version and a folder that is not one: nothing"
        plugin("2.2.0")
        newer = "KISS 2.2.0 is installed; this session runs 2.1.1: start the run in a new session\n"
        assert call(root, "start", R, "PROJECT=" + facts, *start_keys)[1] == newer
        assert call(root, "implementer", R, "ELAPSED=1") == (quiet[0], newer), "the line on stderr; the prompt unchanged"
    with tempfile.TemporaryDirectory() as cache:
        os.makedirs(os.path.join(cache, "2.2.0-alpha.1"))
        root, R = plugin("2.2.0"), os.path.join(cache, "run")
        os.makedirs(R)
        assert call(root, "start", R, "PROJECT=" + facts, *start_keys)[1] == "", "a prerelease ranks below its release"
        os.makedirs(os.path.join(cache, "9.0.0"))                           # a newer folder beside each root below
        for v, manifest, want in (("2.3.0", None, "unknown"), ("2.4.0", ".claude-plugin/plugin.json", "2.4.1")):
            root = os.path.join(cache, v)
            os.makedirs(os.path.join(root, ".claude-plugin"))
            if manifest:
                with open(os.path.join(root, manifest), "w") as f:
                    json.dump({"version": want}, f)
            o, e = call(root, "start", R, "PROJECT=" + facts, *start_keys)
            assert json.load(open(os.path.join(R, "run.json")))["VERSION"] == want, (manifest, o)
            assert (e == "") == (manifest is None), ("no manifest: no newer-version line", manifest, e)
    for rule in ("break it in a scratch copy under /s", "see it fail, and keep the code in W unbroken",
                 "a time bound is only a backstop", "at least 2 times the slowest time the run saw",
                 "run every acceptance line not marked `(reviewer)`", "goes into a `Reviewer checks:` line"):
        assert out.count(rule) == 1, ("the guard, clock and acceptance rules appear once", rule)
    ends = [out.index(w) for w in ("`Mutants:` (each new guard", "`Reviewer checks:` (each acceptance line", "`Skipped:` what", "`Risk:` any risk")]
    assert ends == sorted(ends), "the entry ends Mutants, Reviewer checks, Skipped, Risk"
    assert "fails on the old code" in loop["fix"] and "write a `Risk:` line for that item" in loop["fix"], "a fix is proven on the old code"
    assert ("triage fix-now line found after this review" in sv and "a guard or data change is high" in sv
            and sv.index("triage fix-now line") < sv.index("Write /") ), "triage fix-now lines join the sort with a severity"
    assert "take the next open ticket" not in out and "stop where it says" in out, "a continue's batch and its stop win"
    assert "only the findings of severity critical or high" in loop["recheck"], "the recheck covers only critical or high findings"
    assert "reproduced_in_app" in loop["recheck"] and "diff and the test output" in loop["recheck"]
    assert "a broken command or link" in sv and "a low finding with no effect" in sv, "the sort's bar for a fix"
    assert "merge gate" in sv and "2 fix rounds per review and 3 per run" in sv, "the merge gate log and the round caps"
    assert ("only low or medium findings that touch no guard, data or owner rule are left, there is no gate" in sv
            and "offers them as one kiss-mini task" in sv and "any other finding left asks a gate" in sv), "low leftovers go to one kiss-mini task, the rest to a gate"
    assert 'A finding of medium or higher severity that fits none of these is a "fix"' in sv, "every finding has a bucket"
    assert "Start no subagent of your own" in rv, "the reviewer starts no subagent"
    fx, rc = loop["fix"], loop["recheck"]
    assert 'codegraph sync -q "/w"' in fx and fx.index("Fix each one") < fx.index("codegraph sync -q") < fx.index("Run the acceptance"), "the fix prompt syncs CodeGraph after its edits"
    assert 'codegraph sync -q "/w"' in rc and rc.index("codegraph sync -q") < rc.index("CodeGraph"), "the recheck syncs before it reads with CodeGraph"
    print("prompt selftest ok")


if __name__ == "__main__":
    main(sys.argv)
