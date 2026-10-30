#!/usr/bin/env python3
"""The run's feature list, RUN/tickets.json (SKILL.md, step 2).

  python3 -I tickets.py check RUN        the shape; after `freeze`, also: only `passes` changed
  python3 -I tickets.py freeze RUN       copy tickets.json to tickets.orig.json at the build start
  python3 -I tickets.py render RUN       write issues/<ID>.md, the text briefs.py seeds
  python3 -I tickets.py open RUN         the open tickets, one per line
  python3 -I tickets.py continue RUN [ELAPSED BUDGET]   the controller's message, or nothing when all pass
  python3 -I tickets.py --selftest

One ticket: {"id", "title", "spec", "acceptance": [...], "passes": false} and, optional, "files", "symbols",
"seeds" (hints for the CodeGraph seed), "depends_on" (ids), "risky" (the reviewer also checks it alone).
JSON, not Markdown: an agent edits only `passes`, and `check` refuses any other change.
"""
import json, os, re, sys

ID = re.compile(r"^[A-Z][A-Z0-9]*-[0-9]+$")
OPTIONAL = {"files": list, "symbols": list, "seeds": list, "depends_on": list, "risky": bool}


def load(run, name="tickets.json"):
    with open(os.path.join(run, name)) as f:
        return json.load(f)


def problems(rows, orig=None):
    out = []
    if not isinstance(rows, list) or not rows:
        return ["tickets.json is a non-empty list"]
    ids = [r.get("id") for r in rows if isinstance(r, dict)]
    for i, r in enumerate(rows):
        if not isinstance(r, dict):
            out.append(f"[{i}] is not an object")
            continue
        tid = r.get("id")
        if not isinstance(tid, str) or not ID.match(tid):
            out.append(f"[{i}] id {tid!r}: like T-1")
        for k in ("title", "spec"):
            if not isinstance(r.get(k), str) or not r[k].strip():
                out.append(f"{tid}: {k} is a non-blank string")
        acc = r.get("acceptance")
        if not isinstance(acc, list) or not acc or not all(isinstance(a, str) and a.strip() for a in acc):
            out.append(f"{tid}: acceptance is a non-empty list of non-blank strings (the definition of done)")
        if type(r.get("passes")) is not bool:
            out.append(f"{tid}: passes is true or false")
        for k, t in OPTIONAL.items():
            if k in r and not isinstance(r[k], t):
                out.append(f"{tid}: {k} is a {t.__name__}")
        for d in r.get("depends_on") or []:
            if d not in ids or d == tid:
                out.append(f"{tid}: depends_on {d!r} is not another ticket")
        extra = set(r) - {"id", "title", "spec", "acceptance", "passes"} - set(OPTIONAL)
        if extra:
            out.append(f"{tid}: unknown keys {sorted(extra)}")
    if len(set(ids)) != len(ids):
        out.append("ids repeat")
    if orig is not None:
        if [r.get("id") for r in orig] != ids:
            out.append("tickets were added, removed or moved after the freeze")
        for a, b in zip(orig, rows):
            if isinstance(a, dict) and isinstance(b, dict):
                changed = sorted(k for k in set(a) | set(b) if k != "passes" and a.get(k) != b.get(k))
                if changed:
                    out.append(f"{b.get('id')}: {changed} changed after the freeze; only passes may")
    return out


def open_tickets(rows):
    return [r for r in rows if not r["passes"]]


def continue_text(rows, elapsed=None, budget=None):
    left = open_tickets(rows)
    if not left:
        return ""
    clock = f" Elapsed {elapsed}s / {budget}s." if elapsed is not None and budget is not None else ""
    return ("continue: open tickets " + ", ".join(f"{r['id']} ({r['title']})" for r in left)
            + f". {len(rows) - len(left)} of {len(rows)} pass.{clock} Take the next open ticket.")


def render(run, rows):
    os.makedirs(os.path.join(run, "issues"), exist_ok=True)
    for r in rows:
        body = [f"# {r['id']}: {r['title']}", "", r["spec"].strip(), "", "## Acceptance (the definition of done)", ""]
        body += [f"- {a}" for a in r["acceptance"]]
        if r.get("files"):
            body += ["", "## Files (hints)", ""] + [f"- `{f}`" for f in r["files"]]
        if r.get("symbols"):
            body += ["", "## Symbols (hints)", ""] + [f"- `{s}`" for s in r["symbols"]]
        with open(os.path.join(run, "issues", r["id"] + ".md"), "w") as f:
            f.write("\n".join(body) + "\n")
        r.setdefault("seeds", [])


def selftest():
    good = [{"id": "T-1", "title": "a", "spec": "b", "acceptance": ["c"], "passes": False},
            {"id": "T-2", "title": "d", "spec": "e", "acceptance": ["f"], "passes": False, "depends_on": ["T-1"]}]
    assert problems(good) == []
    assert any("acceptance" in p for p in problems([{**good[0], "acceptance": []}]))
    assert any("passes" in p for p in problems([{**good[0], "passes": "no"}]))
    assert any("depends_on" in p for p in problems([{**good[0], "depends_on": ["T-9"]}]))
    assert any("unknown keys" in p for p in problems([{**good[0], "note": 1}]))
    done = [dict(good[0], passes=True), good[1]]
    assert problems(done, good) == [], "only passes changed: fine"
    assert any("only passes may" in p for p in problems([dict(good[0], title="x"), good[1]], good))
    assert any("added, removed" in p for p in problems([good[0]], good))
    assert continue_text(done, 340, 1200).startswith("continue: open tickets T-2 (d). 1 of 2 pass. Elapsed 340s / 1200s.")
    assert continue_text([dict(r, passes=True) for r in good]) == ""
    print("tickets selftest ok")


def main(argv):
    if argv[1:] == ["--selftest"]:
        return selftest()
    cmd, run = argv[1], argv[2]
    rows = load(run)
    if cmd == "check":
        orig = load(run, "tickets.orig.json") if os.path.exists(os.path.join(run, "tickets.orig.json")) else None
        bad = problems(rows, orig)
        print("\n".join(bad) or f"ok: {len(rows)} tickets, {len(rows) - len(open_tickets(rows))} pass")
        sys.exit(1 if bad else 0)
    if cmd == "freeze":
        assert not problems(rows), "fix `check` first"
        with open(os.path.join(run, "tickets.orig.json"), "w") as f:
            json.dump(rows, f, indent=1)
        print(f"frozen: {len(rows)} tickets")
    elif cmd == "render":
        render(run, rows)
        print(f"rendered {len(rows)} issues")
    elif cmd == "open":
        print("\n".join(f"{r['id']}\t{r['title']}" for r in open_tickets(rows)))
    elif cmd == "continue":
        e, b = (int(argv[3]), int(argv[4])) if len(argv) > 4 else (None, None)
        print(continue_text(rows, e, b))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
