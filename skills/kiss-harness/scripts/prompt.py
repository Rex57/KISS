#!/usr/bin/env python3
"""Print one filled prompt (SKILL.md); the controller gives it to a new subagent or sends it to a running one.

  python3 -I prompt.py start R KEY=VALUE ...                 write the run's values once to R/run.json, with
                                                             VERSION (the running plugin's), and WARN for each
                                                             facts line the run needs and PROJECT lacks
  python3 -I prompt.py <implementer|reviewer|severity|fix|recheck> R [KEY=VALUE ...]
  python3 -I prompt.py handoff R ROUND=<n> [KEY=VALUE ...]   a new implementer's prompt for fix round n: the
                                                             implementer's standing rules (no per-ticket steps),
                                                             then the fix step's prompt of round n
  python3 -I prompt.py wait R <seconds>                      record one owner wait (a gate, a decision, a pause)
  python3 -I prompt.py --selftest

start keys: W (worktree), BR (branch), SCR (scratch folder), MAIN (the main checkout, never touched), PROJECT (the
project facts file), TITLE, BASE, SMOKE, APP. A step takes only the values that change per call: HEAD, ROUND,
FIX_BASE, FIX_HEAD, ELAPSED (a call value wins over run.json). A step reads its file by a fixed name in R: severity
review-<ROUND>.md (the reviewer's findings), fix fix-<ROUND>.md (the fix list), recheck answer-<ROUND>.md (the
implementer's answer); the sort writes sort-<ROUND>.json. Filled here: HB (the skill folder) and CLOCK (ELAPSED and
BUDGET, in seconds: "Time: elapsed 340s of a 1200s budget."). With no ELAPSED in the call, ELAPSED is now minus the
START that `start` wrote in run.json minus each recorded wait (no START: no clock). With ELAPSED and no BUDGET, the
budget is 10 minutes per ticket in R/tickets.json plus 2 hours for the reviews and fix rounds, plus the facts
file's `Full check time:` minutes when it has that line. A value the template
needs that neither run.json nor the call gives is an error that names it. Every call prints a line on stderr when
a KISS version folder beside the running one holds a higher version (in its manifest).
"""
import json, os, re, string, sys, time

HB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(HB))   # the plugin; in a plugin cache, its version folder
MANIFESTS = (".claude-plugin/plugin.json", ".codex-plugin/plugin.json", "gemini-extension.json", ".antigravity-plugin/plugin.json")
FACTS = {"Full check time:": "the budget adds no time for the full check", "Smoke check": "the SMOKE value is the only smoke check",
         "Merge:": "the merge gate asks", "After merge:": "a later commit asks", "Flake check:": "the close starts no flake check",
         "Shared test resources:": "product checks are not held"}   # each line start warns on, and what no line means (D8)
T = os.path.join(HB, "templates")
PER_TICKET_S, REVIEW_S = 600, 7200
STEPS = ("implementer", "reviewer", "severity", "fix", "recheck")
START_KEYS = {"W", "BR", "SCR", "MAIN", "PROJECT", "TITLE", "BASE", "SMOKE", "APP"}
WAIT_FORM = "wait R <seconds>: a whole number of seconds the owner took (a gate, a decision, a pause), after `start`"
# implementer.md's steps that hold for a fix too (CodeGraph, the build and test rules, the checks); its others are per ticket
HANDOFF_STEPS = ("2", "3", "4")
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


def elapsed(run, now=time.time):
    """The run's clock (D4): seconds since run["START"], less the owner waits."""
    return max(0, int(now() - run["START"] - sum(run.get("WAITS", []))))


def fill(step, keys, text=None):
    text = text if text is not None else open(os.path.join(T, step + ".md")).read()
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
    up = os.path.dirname(root)
    vs = [v for v in os.listdir(up) if version_key(v) and version_key(v) > version_key(run) and version(os.path.join(up, v))]
    best = max(vs, key=version_key, default=None)
    return f"KISS {best} is installed; this session runs {run}: start the run in a new session" if best else ""


def save(R, run):
    """Write R/run.json whole: a temporary file, then a rename, so an interrupted write keeps the old file."""
    path = os.path.join(R, "run.json")
    tmp = path + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(run, f, indent=1)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def start(R, values, root=ROOT, now=time.time):
    unknown = sorted(set(values) - START_KEYS)
    if unknown:
        sys.exit(f"start: unknown keys {', '.join(unknown)} (known: {', '.join(sorted(START_KEYS))})")
    v = version(root) or "unknown"
    try:
        with open(os.path.join(R, "run.json")) as f:
            old = json.load(f)
    except (OSError, ValueError):
        old = {}
    # a second start (new values) keeps the run's start time and its waits: the clock goes on
    save(R, dict(values, VERSION=v, START=old.get("START", now()), WAITS=old.get("WAITS", [])))
    out = [f"wrote {os.path.join(R, 'run.json')}: {', '.join(sorted(values))}, VERSION {v}"]
    try:
        with open(values.get("PROJECT", "")) as p:
            text = p.read()
        out += [f"WARN: the facts file has no `{line}` line: {meaning}" for line, meaning in FACTS.items()
                if not re.search(r"^\W*" + re.escape(line), text, re.M)]
    except OSError:
        out.append(f"WARN: no facts file at {values.get('PROJECT', '(no PROJECT)')}")
    return "\n".join(out)


def wait(R, args):
    """Record one owner wait in R/run.json; the clock leaves it out (D4, D10)."""
    if len(args) != 1 or not re.fullmatch(r"\d+", args[0]):
        sys.exit(f"usage: {WAIT_FORM}")
    path = os.path.join(R, "run.json")
    try:
        with open(path) as f:
            run = json.load(f)
    except (OSError, ValueError):
        run = {}
    if "START" not in run:
        sys.exit(f"no start time in {path}: run `prompt.py start` first; usage: {WAIT_FORM}")
    run["WAITS"] = run.get("WAITS", []) + [int(args[0])]
    save(R, run)
    return f"recorded a wait of {args[0]}s in {path}: {sum(run['WAITS'])}s of owner waits in all"


def handoff_text():
    """The head of a fix round's handoff: implementer.md's paragraphs before its per-ticket steps (not its first) and
    its HANDOFF_STEPS, renumbered; read from the template, never copied."""
    head, steps = open(os.path.join(T, "implementer.md")).read().split("For each open ticket:\n", 1)
    items = [i for i in re.split(r"\n(?=\d+\. )", steps.split("\n\n", 1)[0].strip()) if i.split(". ", 1)[0] in HANDOFF_STEPS]
    return ("Read `$R/progress.md` first: you are a new implementer of $TITLE, for fix round $ROUND, and that file holds "
            "the work so far.\n\n" + "\n\n".join(head.strip().split("\n\n")[1:]) + "\n\nFor each item of the fix list below:\n"
            + "\n".join(f"{n}. {i.split('. ', 1)[1]}" for n, i in enumerate(items, 1)) + "\n")


def prompt(step, R, call, now=time.time):
    """The step's template filled from R/run.json, the call's values and the step's fixed-name file."""
    path = os.path.join(R, "run.json")
    if not os.path.isfile(path):
        sys.exit(f"no {path}: run `prompt.py start {R} KEY=VALUE ...` first")
    with open(path) as f:
        keys = dict(json.load(f), **call, R=R)
    if "ELAPSED" not in call and "START" in keys:           # D4: no ELAPSED typed by hand
        keys["ELAPSED"] = elapsed(keys, now)
    if step == "handoff":
        return fill(step, keys, handoff_text()) + "\n" + prompt("fix", R, call, now)
    if step in FILES:
        if "ROUND" not in keys:
            sys.exit(f"{step}: missing ROUND")
        name, pattern = FILES[step]
        p = os.path.join(R, pattern.format(keys["ROUND"]))
        if not os.path.isfile(p):
            sys.exit(f"{step}: missing {p}")
        keys[name] = open(p).read().strip()
        if step == "fix" and re.search(r"\bfull check\b", keys[name], re.I):   # the implementer never runs it (T-7)
            print("WARN: the fix list asks for the full check: the controller runs it once at the end; name the tests instead",
                  file=sys.stderr)
    return fill(step, keys)


def main(argv, root=ROOT, now=time.time):
    if argv[1:] == ["--selftest"]:
        return selftest()
    if len(argv) < 3 or argv[1] not in ("start", "wait", "handoff") + STEPS or "=" in argv[2]:
        sys.exit(__doc__)
    if argv[1] == "wait":
        return print(wait(os.path.abspath(argv[2]), argv[3:]))
    step, R, values = argv[1], os.path.abspath(argv[2]), pairs(argv[3:])
    warn = newer(root)
    if warn:
        print(warn, file=sys.stderr)
    print(start(R, values, root, now) if step == "start" else prompt(step, R, values, now))


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
            assert "Models" not in o, o                                     # an optional line: no WARN
            if warned == list(six):
                assert warns == [
                    "WARN: the facts file has no `Full check time:` line: the budget adds no time for the full check",
                    "WARN: the facts file has no `Smoke check` line: the SMOKE value is the only smoke check",
                    "WARN: the facts file has no `Merge:` line: the merge gate asks",
                    "WARN: the facts file has no `After merge:` line: a later commit asks",
                    "WARN: the facts file has no `Flake check:` line: the close starts no flake check",
                    "WARN: the facts file has no `Shared test resources:` line: product checks are not held"], warns
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
        os.makedirs(os.path.join(cache, "2.10.0"))
        assert call(root, "start", R, "PROJECT=" + facts, *start_keys)[1] == "", "a folder with no manifest holds no version"
        plugin("9.0.0")                                                     # a newer version beside each root below
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
    assert "Leave a page's `Reviewed` date as it is" in out, "the date is the close's (D25)"
    assert ("one `codegraph explore` per symbol of the ticket (its source, its call lines and its tests; a long caller list is cut short"
            in out and "step 2's `callers --limit 100` still reads them all" in out), "the seed is a reading aid; step 2's callers stays"
    fx, rc = loop["fix"], loop["recheck"]
    assert "round 1 of your findings, or work from an owner decision, with the commits a1..b2" in rc, "the recheck's round: findings or decision work (D21)"
    assert re.search(r"For each owner decision in \S+/fix-1\.md: judge its commits in that range by your rubric A to G, and check each of its `\(reviewer\)` lines in the running product\.", rc), rc
    assert sv.count("touches an owner rule only when it breaks that ruling or its acceptance line") == 1, "one definition (D2)"
    assert re.search(r"Never touch the main checkout /m, a live system \(except the exact read-only commands a ruling in \S+/decisions\.md names\), ssh or a git remote\.", rv), "D7"
    assert "with no ruling, report that line in cannot_check and do not run it" in rv and "names its `D<n>`" in rv, "a live read, with a ruling and with none"
    assert rv.count("Read and run the code at def from your own clone under /s, because the implementer may still build in W; CodeGraph on W may then show newer code, so check a line against your clone.") == 1, rv
    assert "so check a line against your clone. Where the start command names W, use your clone in its place." in rv, rv
    assert "Read and run the code at b2 from a fresh clone under /s, because a clone at an older head reports a fixed item as not fixed." in loop["recheck"], loop["recheck"]
    assert 'git clone -q "/w" "/s/<name>"' in rv and 'git -C "/s/<name>" checkout -q --detach def' in rv, "the reviewer's copy is a clone (D24)"
    for name in sorted(os.listdir(T)) + ["../SKILL.md"]:
        assert "archive" not in open(os.path.join(T, name)).read(), name       # no template or step tells a reviewer to use git archive
    assert 'codegraph sync -q "/w"' in fx and fx.index("Fix each one") < fx.index("codegraph sync -q") < fx.index("Run the acceptance"), "the fix prompt syncs CodeGraph after its edits"
    assert 'codegraph sync -q "/w"' in rc and rc.index("codegraph sync -q") < rc.index("CodeGraph"), "the recheck syncs before it reads with CodeGraph"
    # D4: the clock from R/run.json (a fixed clock): now minus the start minus the owner waits; a call value wins
    with tempfile.TemporaryDirectory() as R:
        with open(os.path.join(R, "tickets.json"), "w") as f:
            json.dump([{"id": "T-1"}], f)
        clock = [1_000_000.0]

        def at(*argv):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                main(["prompt.py", *argv], now=lambda: clock[0])
            return buf.getvalue()

        def refused(*argv):
            try:
                at(*argv)
            except SystemExit as x:
                return str(x)
            raise AssertionError(f"must stop: {argv}")
        assert "wait R <seconds>" in refused("wait", R, "120"), "a wait before start"
        assert not os.path.exists(os.path.join(R, "run.json"))
        at("start", R, "PROJECT=/w/.kiss/project.md", *start_keys)
        at("wait", R, "120")
        at("wait", R, "120")
        clock[0] += 1000
        assert "Time: elapsed 760s of a 7800s budget." in at("implementer", R), "1,000 s on, two waits of 120 s"
        assert "Time: elapsed 5s of a 7800s budget." in at("implementer", R, "ELAPSED=5"), "a call value wins"
        kept = open(os.path.join(R, "run.json")).read()
        for bad in ("abc", "-5", "1.5", ""):
            assert "wait R <seconds>" in refused("wait", R, bad), bad
            assert open(os.path.join(R, "run.json")).read() == kept, bad
        assert "wait R <seconds>" in refused("wait", R), "no seconds"
        at("start", R, "PROJECT=/w/.kiss/project.md", *start_keys)          # a second start keeps the start and the waits
        assert "Time: elapsed 760s of" in at("reviewer", R, "HEAD=h"), "start again: the clock goes on"
        try:                                                                 # a write interrupted before it lands
            save(R, {"START": 1, "WAITS": [object()]})
            raise AssertionError("an unwritable value must fail")
        except TypeError:
            pass
        assert open(os.path.join(R, "run.json")).read() == kept and sorted(os.listdir(R)) == ["run.json", "tickets.json"], os.listdir(R)
        # the fix-round handoff: the implementer's standing rules, then round 2's fix prompt; no per-ticket steps
        with open(os.path.join(R, "fix-2.md"), "w") as f:
            f.write("FIX-LIST-TWO")
        ho, impl = at("handoff", R, "ROUND=2"), at("implementer", R)
        fix2 = at("fix", R, "ROUND=2")
        assert ho.startswith(f"Read `{R}/progress.md` first"), ho[:200]
        assert ho.rstrip().endswith(fix2.rstrip()) and "FIX-LIST-TWO" in ho, "it ends with the fix step's prompt"
        for rule in ("ponytail:ponytail", "mattpocock-skills:tdd", 'codegraph node -p "/w" <name>', 'codegraph callers -p "/w" --limit 100',
                     "cgcallers.py", "Never relax the limit", "Never touch the main checkout /m", "Never the full check"):
            assert ho.count(rule) == 1, ("a standing rule, once", rule)
        for step in ("You build the open tickets", "1. Seed it", "Stage the ticket's files", 'set this ticket\'s "passes"',
                     "When no ticket is open", 'After a ticket marked "risky"'):
            assert step not in ho, ("no per-ticket step", step)
            assert step in impl, ("the implementer keeps it", step)
        for text in (fix2, ho):                     # F16: the commit step in the fix prompt, which the handoff ends with
            assert "callcheck.py" in text and "explicit path" in text and "as before" not in text, text
        assert "missing ROUND" in refused("handoff", R) and "fix-3.md" in refused("handoff", R, "ROUND=3")
        # T-7: a fix list that asks for the full check: one WARN on stderr, the whole prompt on stdout
        with open(os.path.join(R, "fix-4.md"), "w") as f:
            f.write("- F1: the guard misses a case; then run the full check")
        o, e = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(o), contextlib.redirect_stderr(e):
            main(["prompt.py", "fix", R, "ROUND=4"], now=lambda: clock[0])
        assert e.getvalue() == ("WARN: the fix list asks for the full check: the controller runs it once at the end; "
                                "name the tests instead\n"), e.getvalue()
        assert "F1: the guard misses a case" in o.getvalue() and o.getvalue().rstrip().endswith('"not_fixed": [{"id": "", "why": ""}]}'), o.getvalue()
        e = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(e):
            main(["prompt.py", "fix", R, "ROUND=2"], now=lambda: clock[0])
        assert e.getvalue() == "", "no full check asked: no WARN"
    assert ("You build the open tickets in" in out and "at most 3 open tickets per turn" in out
            and "end your turn with one line that names the tickets you built and the next open one" in out), "D2: batches of 3"
    print("prompt selftest ok")


if __name__ == "__main__":
    main(sys.argv)
