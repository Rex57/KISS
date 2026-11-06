#!/usr/bin/env python3
"""The run's feature list, RUN/tickets.json (SKILL.md, step 2).

  python3 -I tickets.py check RUN        the shape; after `freeze`, also: only `passes` changed; a WARN (exit 0)
                                         for a ticket that lists code files that exist in the repo of RUN, and no
                                         symbols, and for each symbol that repo's CodeGraph index does not hold
  python3 -I tickets.py freeze RUN       copy tickets.json to tickets.orig.json at the build start
  python3 -I tickets.py render RUN       write issues/<ID>.md, the text briefs.py seeds
  python3 -I tickets.py open RUN         the open tickets, one per line
  python3 -I tickets.py continue RUN [ELAPSED BUDGET] [--review ID]   the controller's message, or nothing when all
                                         pass; with --review (a risky ticket under review alone), only the open
                                         tickets that do not depend on it, up to the first risky one, or nothing
                                         when all of them do; plus the hold of the product checks when the facts
                                         file's `Shared test resources:` line says "one at a time"
  python3 -I tickets.py --selftest

One ticket: {"id", "title", "spec", "acceptance": [...], "passes": false} and, optional, "files", "symbols",
"seeds" (hints for the CodeGraph seed), "depends_on" (ids), "risky" (the reviewer also checks it alone).
JSON, not Markdown: an agent edits only `passes`, and `check` refuses any other change.
"""
import json, os, re, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import briefs  # noqa: E402  (the index lookup is briefs.py's own)

ID = re.compile(r"^[A-Z][A-Z0-9]*-[0-9]+$")
OPTIONAL = {"files": list, "symbols": list, "seeds": list, "depends_on": list, "risky": bool}
# shortcut: a fixed list of code file types (check runs without W's index); add a type when a project needs it
CODE = {".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".svelte", ".vue", ".go", ".rs", ".java", ".kt", ".swift",
        ".rb", ".php", ".c", ".h", ".cc", ".cpp", ".cs", ".sh"}


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


def warnings(rows, root):
    """A code ticket with no symbols gets a seed with no node or callers: warn, never fail. Only code files that exist
    in root (the repo that holds the run) count: a new file has no symbol yet."""
    return [f"WARN {r['id']}: lists code files and no symbols: its seed holds no node or callers" for r in rows
            if not r.get("symbols") and any(os.path.splitext(f)[1] in CODE and os.path.isfile(os.path.join(root, f))
                                            for f in r.get("files") or [])]


def unindexed(rows, root, run=briefs.run):
    """A WARN for each ticket symbol root's index does not hold, never a failure: a ticket may name one it creates."""
    if not os.path.isdir(os.path.join(root, ".codegraph")):
        return [f"symbol check skipped: no CodeGraph index in {root}"]
    try:
        return [f"WARN {r['id']}: symbol {s} is not in the index (fine when the ticket creates it)"
                for r in rows for s in r.get("symbols") or [] if not briefs.exists(root, s, run)]
    except (OSError, subprocess.TimeoutExpired):
        return ["symbol check skipped: codegraph did not run"]


def open_tickets(rows):
    return [r for r in rows if not r["passes"]]


def waits_for(rows, tid):
    """The ids of the tickets that depend on tid, directly or through another ticket."""
    deps = {r["id"]: set(r.get("depends_on") or []) for r in rows}
    out, grew = set(), True
    while grew:
        more = {i for i, d in deps.items() if d & (out | {tid})} - out
        out, grew = out | more, bool(more)
    return out


def one_at_a_time(run):
    """True when the facts file of run/run.json has a `Shared test resources:` line that says "one at a time" (D17)."""
    try:
        with open(os.path.join(run, "run.json")) as f, open(json.load(f)["PROJECT"]) as p:
            return any(re.match(r"\W*Shared test resources:", l) and "one at a time" in l.lower() for l in p)
    except (OSError, KeyError, ValueError, TypeError):
        return False


def continue_text(rows, elapsed=None, budget=None, review=None, hold=False):
    left = open_tickets(rows)
    wait = waits_for(rows, review) if review else set()
    go = [r for r in left if r["id"] not in wait and r["id"] != review]
    if not go:
        return ""
    stop = next((r["id"] for r in go if r.get("risky")), None) if review else None
    if stop:                                                   # a risky ticket keeps its own solo review
        go = go[:[r["id"] for r in go].index(stop) + 1]
    clock = f" Elapsed {elapsed}s / {budget}s." if elapsed is not None and budget is not None else ""
    text = ("continue: open tickets " + ", ".join(f"{r['id']} ({r['title']})" for r in go)
            + f". {len(rows) - len(left)} of {len(rows)} pass.{clock}")
    if not review:
        return text + " Take the next open ticket."
    waiting = [r["id"] for r in left if r["id"] in wait]
    return (text + " Build only these, then stop with your final message"
            + (f"; do not start {', '.join(waiting)} until the review of {review} is done." if waiting else ".")
            + f" {review} is under review alone: its fix round comes at your next stop."
            + (f" {stop} is risky: stop after it." if stop else "")
            + (' Hold your product checks until the controller sends "product free".' if hold else ""))


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


def selftest():
    import contextlib, io
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
    four = [dict(good[0], passes=True, risky=True), dict(good[1], id="T-2"),
            dict(good[1], id="T-3", title="g", depends_on=["T-2"]), dict(good[0], id="T-4", title="h")]
    assert continue_text(four, review="T-1") == (
        "continue: open tickets T-4 (h). 1 of 4 pass. Build only these, then stop with your final message; do not "
        "start T-2, T-3 until the review of T-1 is done. T-1 is under review alone: its fix round comes at your next "
        "stop."), continue_text(four, review="T-1")
    assert continue_text(four, review="T-2") == (                       # an open ticket under review is not to take
        "continue: open tickets T-4 (h). 1 of 4 pass. Build only these, then stop with your final message; do not "
        "start T-3 until the review of T-2 is done. T-2 is under review alone: its fix round comes at your next "
        "stop."), continue_text(four, review="T-2")
    assert continue_text(four[:3], review="T-1") == "", "every open ticket waits for the risky one: no message"
    assert continue_text(four) == "continue: open tickets T-2 (d), T-3 (g), T-4 (h). 1 of 4 pass. Take the next open ticket."
    risky = [dict(good[0], passes=True, risky=True), dict(good[1], id="T-2", depends_on=[]),
             dict(good[1], id="T-3", title="g", depends_on=[], risky=True), dict(good[0], id="T-4", title="h")]
    assert continue_text(risky, review="T-1") == (                       # the batch ends at its first risky ticket
        "continue: open tickets T-2 (d), T-3 (g). 1 of 4 pass. Build only these, then stop with your final message. "
        "T-1 is under review alone: its fix round comes at your next stop. T-3 is risky: stop after it."), continue_text(risky, review="T-1")
    assert continue_text(risky) == "continue: open tickets T-2 (d), T-3 (g), T-4 (h). 1 of 4 pass. Take the next open ticket."
    import tempfile
    hold = ' Hold your product checks until the controller sends "product free".'
    with tempfile.TemporaryDirectory() as run:                           # the hold reads the facts file of run.json
        with open(os.path.join(run, "tickets.json"), "w") as f:
            json.dump(four, f)
        facts = os.path.join(run, "project.md")
        with open(os.path.join(run, "run.json"), "w") as f:
            json.dump({"PROJECT": facts}, f)
        for body, held in (("- Shared test resources: one Postgres; One at a time.\n", True),
                           ("- Shared test resources: one Postgres, 3 sessions at once\n", False),
                           ("- Merge: ask\n- Note: one at a time is fine\n", False), (None, False)):
            if body is not None:
                with open(facts, "w") as f:
                    f.write(body)
            elif os.path.exists(facts):
                os.remove(facts)
            for argv, want in ((["--review", "T-1"], continue_text(four, review="T-1") + (hold if held else "")),
                               ([], continue_text(four))):              # the plain continue never holds
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    main(["tickets.py", "continue", run, *argv])
                assert out.getvalue() == want + "\n", (body, argv, out.getvalue())
    with tempfile.TemporaryDirectory() as root:                          # the repo that holds R
        os.makedirs(os.path.join(root, "app"))
        open(os.path.join(root, "app", "x.py"), "w").close()
        code = dict(good[0], files=["app/x.py", "README.md"])
        assert warnings([code], root) == ["WARN T-1: lists code files and no symbols: its seed holds no node or callers"]
        assert warnings([dict(code, symbols=["f"])], root) == [] and warnings([dict(good[0], files=["README.md", "a.json"])], root) == []
        assert warnings([dict(good[0], files=["app/new.py", "README.md"])], root) == [], "a new code file: no WARN"
    with tempfile.TemporaryDirectory() as run:
        with open(os.path.join(run, "tickets.json"), "w") as f:
            json.dump(four, f)
        for bad in (["--review=T-1"], ["--review", "T-9"], ["--review"]):    # refused, never ignored
            try:
                main(["tickets.py", "continue", run, *bad])
                raise AssertionError(f"must stop: {bad}")
            except SystemExit as x:
                assert x.code and x.code != 0, (bad, x.code)
        try:
            main(["tickets.py", "continue", run, "--review=T-1"])
        except SystemExit as x:
            assert x.code == __doc__, "--review=ID: the usage text"
        render(run, [dict(good[0], files=["a.py"], symbols=["f"], seeds=["q"])])     # the issue file, as before
        assert open(os.path.join(run, "issues", "T-1.md")).read() == (
            "# T-1: a\n\nb\n\n## Acceptance (the definition of done)\n\n- c\n\n## Files (hints)\n\n- `a.py`\n\n"
            "## Symbols (hints)\n\n- `f`\n"), open(os.path.join(run, "issues", "T-1.md")).read()
    held = [{"name": "read", "qualifiedName": "Lsp::read"}, {"name": "f", "qualifiedName": "f"}]
    fake = lambda *a, timeout=120: subprocess.CompletedProcess(a, 0, json.dumps([{"node": n} for n in held]), "")
    with tempfile.TemporaryDirectory() as root:                          # a repo whose run R is <root>/.kiss/runs/r
        run = os.path.join(root, ".kiss", "runs", "r")
        os.makedirs(run)
        with open(os.path.join(run, "tickets.json"), "w") as f:
            json.dump([dict(good[0], symbols=["Lsp.read", "f", "made_here"]), dict(good[1], symbols=["Lsp::read"])], f)
        for index, want in ((False, ["symbol check skipped: no CodeGraph index in " + root]),
                            (True, ["WARN T-1: symbol made_here is not in the index (fine when the ticket creates it)"])):
            if index:
                os.makedirs(os.path.join(root, ".codegraph"))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                try:
                    main(["tickets.py", "check", run], lookup=fake)
                except SystemExit as x:
                    assert x.code == 0, x.code                            # a WARN never fails the check
            assert out.getvalue().splitlines() == want + ["ok: 2 tickets, 0 pass"], out.getvalue()
    gone = lambda *a, timeout=120: (_ for _ in ()).throw(FileNotFoundError("codegraph"))
    assert unindexed([dict(good[0], symbols=["f"])], root="/no/such/repo", run=gone) == ["symbol check skipped: no CodeGraph index in /no/such/repo"]
    with tempfile.TemporaryDirectory() as root:                          # an index, but no codegraph on PATH
        os.makedirs(os.path.join(root, ".codegraph"))
        assert unindexed([dict(good[0], symbols=["f"])], root, gone) == ["symbol check skipped: codegraph did not run"]
    for argv in (["tickets.py"], ["tickets.py", "check"], ["tickets.py", "nope", "/no/such/run"]):   # the usage, no traceback
        try:
            main(argv)
            raise AssertionError(f"must stop: {argv}")
        except SystemExit as x:
            assert x.code == __doc__, (argv, x.code)
    print("tickets selftest ok")


def main(argv, lookup=briefs.run):
    if argv[1:] == ["--selftest"]:
        return selftest()
    if len(argv) < 3 or argv[1] not in ("check", "freeze", "render", "open", "continue"):
        sys.exit(__doc__)
    cmd, run = argv[1], argv[2]
    rows = load(run)
    if cmd == "check":
        orig = load(run, "tickets.orig.json") if os.path.exists(os.path.join(run, "tickets.orig.json")) else None
        bad = problems(rows, orig)
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(run))))   # <repo>/.kiss/runs/<run>
        warn = warnings(rows, root) + unindexed(rows, root, lookup)
        print("\n".join(bad + warn) if bad else "\n".join(warn + [
            f"ok: {len(rows)} tickets, {len(rows) - len(open_tickets(rows))} pass"]))
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
        review = None
        if any(a.startswith("--review=") for a in argv):
            sys.exit(__doc__)
        if "--review" in argv:
            i = argv.index("--review")
            review, argv = "".join(argv[i + 1:i + 2]), argv[:i] + argv[i + 2:]
            if review not in {r["id"] for r in rows}:
                sys.exit(f"--review {review!r}: not a ticket id")
        e, b = (int(argv[3]), int(argv[4])) if len(argv) > 4 else (None, None)
        print(continue_text(rows, e, b, review, hold=bool(review) and one_at_a_time(run)))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
