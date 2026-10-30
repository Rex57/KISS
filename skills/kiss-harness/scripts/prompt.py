#!/usr/bin/env python3
"""Print one filled prompt (SKILL.md); the controller gives it to a new subagent or sends it to a running one.

  python3 -I prompt.py <implementer|reviewer|severity|fix|recheck> KEY=VALUE ...
  python3 -I prompt.py --selftest

Keys are the template's $NAMES: R (run folder), W (worktree), BR (branch), SCR (scratch folder), MAIN (the main
checkout, never touched), PROJECT (the project facts file), TITLE, BASE, HEAD, SMOKE, APP, ROUND, FIX_BASE,
FIX_HEAD; FINDINGS=@file and ANSWER=@file read a file. Filled here: HB (the skill folder) and CLOCK (ELAPSED and
BUDGET, in seconds: "Time: elapsed 340s of a 1200s budget."; empty without ELAPSED). With ELAPSED and no BUDGET,
the budget is 10 minutes per ticket in R/tickets.json plus 2 hours for the reviews and fix rounds. A key the
template names and nobody gave is an error.
"""
import json, os, re, string, sys

HB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T = os.path.join(HB, "templates")
PER_TICKET_S, REVIEW_S = 600, 7200


def budget(run):
    """Seconds for a run: 10 min per ticket in run/tickets.json, plus 2 h."""
    with open(os.path.join(run, "tickets.json")) as f:
        return PER_TICKET_S * len(json.load(f)) + REVIEW_S


def fill(step, keys):
    text = open(os.path.join(T, step + ".md")).read()
    keys = {k: (open(v[1:]).read().strip() if isinstance(v, str) and v.startswith("@") else v) for k, v in keys.items()}
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


def selftest():
    base = dict(R="/r", W="/w", BR="b", SCR="/s", MAIN="/m", PROJECT="/w/.kiss/project.md", TITLE="T", BASE="abc",
                SMOKE="python3 tests/x.py")
    out = fill("implementer", dict(base, ELAPSED="340", BUDGET="1200"))
    assert "Time: elapsed 340s of a 1200s budget." in out and "/w/.kiss/project.md" in out
    try:
        fill("reviewer", base)
        raise AssertionError("a missing key must stop")
    except SystemExit as x:
        assert "HEAD" in str(x) and "APP" in str(x)
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "tickets.json"), "w") as f:
            json.dump([{"id": f"T-{i}"} for i in range(11)], f)
        assert budget(d) == 13800, "11 tickets: 3 h 50 min"
        assert "of a 13800s budget" in fill("implementer", dict(base, R=d, ELAPSED="5"))
    for step in ("severity", "fix", "recheck"):
        fill(step, dict(base, HEAD="def", APP="a", ROUND="1", FIX_BASE="a", FIX_HEAD="b", FINDINGS="[]", ANSWER="{}"))
    print("prompt selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        selftest()
    else:
        print(fill(sys.argv[1], dict(a.split("=", 1) for a in sys.argv[2:])))
