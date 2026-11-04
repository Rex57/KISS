#!/usr/bin/env python3
"""Print one filled prompt (SKILL.md); the controller gives it to a new subagent or sends it to a running one.

  python3 -I prompt.py start R KEY=VALUE ...                 write the run's values once to R/run.json
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
needs that neither run.json nor the call gives is an error that names it.
"""
import json, os, re, string, sys

HB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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


def start(R, values):
    unknown = sorted(set(values) - START_KEYS)
    if unknown:
        sys.exit(f"start: unknown keys {', '.join(unknown)} (known: {', '.join(sorted(START_KEYS))})")
    with open(os.path.join(R, "run.json"), "w") as f:
        json.dump(values, f, indent=1)
    return f"wrote {os.path.join(R, 'run.json')}: {', '.join(sorted(values))}"


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


def main(argv):
    if argv[1:] == ["--selftest"]:
        return selftest()
    if len(argv) < 3 or argv[1] not in ("start",) + STEPS or "=" in argv[2]:
        sys.exit(__doc__)
    step, R, values = argv[1], os.path.abspath(argv[2]), pairs(argv[3:])
    print(start(R, values) if step == "start" else prompt(step, R, values))


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
            assert f"of a {want}s budget" in run("implementer", R, "ELAPSED=0"), ("D8: the full check time", body)
        run("start", R, "PROJECT=/w/.kiss/project.md", *start_keys)
        assert os.path.exists(os.path.join(HB, "references", "traps.md"))
        for text in (out, rv):   # every agent of a run reads the same traps
            assert HB + "/references/traps.md" in text
    assert "mattpocock-skills:tdd" in out and "Skipped:" in out and "Risk:" in out
    assert "longer than about 2 minutes goes in the background" in out and "never a sleep or poll loop" in out, "D8"
    for rule in ("at least three kinds of bad input", "sweeps every file type", "Never relax the limit or the expected value"):
        assert out.count(rule) == 1, ("D7", rule)
    assert "write a `Risk:` line instead" in out, "D7: the never-relax rule names its Risk line"
    assert "Triage" in rv and "check that each settlement holds" in rv and "do not report a settled line again as new" in rv, "D6"
    assert 'codegraph node -p "/w" <name>` for each function the ticket changes' in out and "Never `grep" in out, "B2"
    for rule in ("codegraph node -p", "codegraph callers -p", "cgcallers.py", "codegraph sync -q", "codegraph affected",
                 "Never the full check", "by explicit path", "callcheck.py"):
        assert out.count(rule) == 1, ("T-5: each rule once", rule)
    assert re.search(r'callcheck\.py" -p "/w" --cached`.*keep its output for step 6.*`## <ID> <commit>`, the callcheck output from step 5', out, re.S), "T-3, R16"
    assert "read every `[grep only]` and `[lsp]` line" in out, "R15"
    assert "ponytail:ponytail-review" in rv and "G. Risk, load and speed" in rv and "A|B|C|D|E|F|G" in rv
    assert "failed before" in loop["fix"] and '"test":' in loop["fix"], "A1: each fix names its test"
    assert "only the findings of severity critical or high" in loop["recheck"], "A1: recheck by severity"
    assert "reproduced_in_app" in loop["recheck"] and "diff and the test output" in loop["recheck"]
    assert "a broken command or link" in sv and "a low finding with no effect" in sv, "A2: the fix bar"
    assert "merge gate" in sv and "2 fix rounds per review and 3 per run" in sv, "A2: log and round caps"
    assert ("only low or medium findings that touch no guard, data or owner rule are left, there is no gate" in sv
            and "offers them as one kiss-mini task" in sv and "any other finding left asks a gate" in sv), "D10"
    assert 'A finding of medium or higher severity that fits none of these is a "fix"' in sv, "F8: every finding has a bucket"
    assert "Start no subagent of your own" in rv, "A4"
    fx, rc = loop["fix"], loop["recheck"]
    assert 'codegraph sync -q "/w"' in fx and fx.index("Fix each one") < fx.index("codegraph sync -q") < fx.index("Run the acceptance"), "T-7: fix syncs after its edits"
    assert 'codegraph sync -q "/w"' in rc and rc.index("codegraph sync -q") < rc.index("CodeGraph"), "T-7: recheck syncs before CodeGraph"
    print("prompt selftest ok")


if __name__ == "__main__":
    main(sys.argv)
