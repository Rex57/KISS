#!/usr/bin/env python3
"""Sort kiss-code-clean's candidates and write the ranked list (SKILL.md step 7).

  python3 -I rank.py ROWS.json OUT.md
  python3 -I rank.py --selftest

ROWS.json: {"skipped": ["<one line per skipped part>"], "rows": [{"kind": "", "where": "file:line",
"evidence": "", "strength": "", "build": "", "hot": false}]}. Kind first: (1) bug or security, (2) risky (code with
no test), (3) load or slow, (4) delete, merge, split or deepen, (5) shortcut; then strength: Strong, Worth exploring,
Speculative; then a hot spot first. An unknown kind or strength, or an OUT that exists, stops with exit 2.
"""
import json, os, sys

KINDS = {"bug": 1, "security": 1, "risky": 2, "load": 3, "slow": 3, "delete": 4, "merge": 4, "split": 4, "deepen": 4,
         "shortcut": 5}
STRENGTHS = {"Strong": 1, "Worth exploring": 2, "Speculative": 3}


def rank(rows):
    bad = [r for r in rows if r.get("kind") not in KINDS or r.get("strength") not in STRENGTHS]
    if bad:
        print("unknown kind or strength: %s" % json.dumps(bad), file=sys.stderr)
        sys.exit(2)
    return sorted(rows, key=lambda r: (KINDS[r["kind"]], STRENGTHS[r["strength"]], not r.get("hot")))


def table(data):
    cell = lambda v: str(v).replace("|", "\\|").replace("\n", " ")
    lines = list(data.get("skipped", [])) + ["", "| # | Kind | Where | Evidence | Strength | Build | Hot |",
                                               "|---|---|---|---|---|---|---|"]
    for n, r in enumerate(rank(data["rows"]), 1):
        lines.append("| %d | %s | %s |" % (n, " | ".join(cell(r.get(k, "")) for k in ("kind", "where", "evidence", "strength", "build")),
                                           "yes" if r.get("hot") else ""))
    return "\n".join(lines).lstrip("\n") + "\n"


def selftest():
    rows = [{"kind": "shortcut", "where": "a.py:1", "strength": "Strong"},
            {"kind": "deepen", "where": "b.py:2", "strength": "Speculative"},
            {"kind": "bug", "where": "c.py:3", "strength": "Worth exploring"},
            {"kind": "merge", "where": "d.py:4", "strength": "Strong"},
            {"kind": "security", "where": "e.py:5", "strength": "Strong"},
            {"kind": "load", "where": "f.py:6", "strength": "Speculative"},
            {"kind": "risky", "where": "g.py:7", "strength": "Worth exploring"},
            {"kind": "delete", "where": "h.py:8", "strength": "Strong", "hot": True},
            {"kind": "split", "where": "i.py:9", "strength": "Worth exploring"}]
    want = ["e.py:5", "c.py:3", "g.py:7", "f.py:6", "h.py:8", "d.py:4", "i.py:9", "b.py:2", "a.py:1"]
    for order in (rows, rows[::-1], rows[3:] + rows[:3]):          # any input order gives the same list
        got = [r["where"] for r in rank(order)]
        assert got == want, got
    out = table({"skipped": ["ponytail not installed: no audit report, no debt ledger"],
                 "rows": [{"kind": "bug", "where": "x.py:1", "evidence": "a|b", "strength": "Strong", "build": "kiss-mini"},
                          {"kind": "bug", "where": "y.py:2", "evidence": "c", "strength": "Strong", "build": "harness", "hot": True}]})
    assert out.splitlines() == ["ponytail not installed: no audit report, no debt ledger", "",
                                "| # | Kind | Where | Evidence | Strength | Build | Hot |", "|---|---|---|---|---|---|---|",
                                "| 1 | bug | y.py:2 | c | Strong | harness | yes |",
                                "| 2 | bug | x.py:1 | a\\|b | Strong | kiss-mini |  |"], out
    try:
        rank([{"kind": "style", "strength": "Strong"}])
        raise AssertionError("an unknown kind must stop")
    except SystemExit as x:
        assert x.code == 2
    print("rank selftest ok")


def main(argv):
    if argv[1:] == ["--selftest"]:
        return selftest()
    if len(argv) != 3:
        sys.exit(__doc__)
    if os.path.exists(argv[2]):
        print("exists: %s (add -2, -3, ... to the name)" % argv[2], file=sys.stderr)
        sys.exit(2)
    data = json.load(open(argv[1]))
    text = table(data)
    os.makedirs(os.path.dirname(os.path.abspath(argv[2])), exist_ok=True)
    with open(argv[2], "x") as f:
        f.write(text)
    print(text, end="")


if __name__ == "__main__":
    main(sys.argv)
