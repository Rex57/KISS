#!/usr/bin/env python3
"""The memory gate of kiss-dream (SKILL.md, step 2): checks one memory folder (notes plus the MEMORY.md index).

  python3 -I check_memory.py MEMDIR
  python3 -I check_memory.py --selftest

FAIL: a note without frontmatter name, description and type (flat `type:` or nested `metadata:` / `  type:`), a
name that does not match its file, a note missing from the index or listed twice, an index line pointing to no
note, an index of 200 lines or more or 25 KB or more, an index line over 150 characters, a secret.
warn: a [[link]] to a note not yet written, a relative date ("yesterday", "last week", "3 days ago").
Exit 1 on any FAIL.
"""
import os, re, sys

INDEX = "MEMORY.md"
MAX_LINES, MAX_BYTES, MAX_LINE = 200, 25 * 1024, 150
LINK = re.compile(r"\]\(([^)\s]+\.md)\)")
WIKI = re.compile(r"\[\[([^\]|#]+)")
SECRET = re.compile(r"(?i)(password|passwd|api[_-]?key|secret|token)\s*[:=]\s*\S{6,}"
                    r"|\b(sk-[A-Za-z0-9]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[abp]-[A-Za-z0-9-]{10,})"
                    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----")
RELATIVE = re.compile(r"(?i)\b(yesterday|today|tomorrow|tonight|recently|(last|next|this) (week|month|year)"
                      r"|\d+ (days?|weeks?|months?) ago)\b")


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def frontmatter(text):
    """{key: value} of the frontmatter; a nested `metadata:` block's keys count as top-level ones."""
    m = re.match(r"---\r?\n(.*?)\r?\n---", text, re.S)
    if not m:
        return None
    return dict(re.findall(r"^[ \t]*([\w-]+):[ \t]*(\S.*?)[ \t]*$", m.group(1), re.M))


def check(memdir):
    fail, warn = [], []
    notes = sorted(f for f in os.listdir(memdir) if f.endswith(".md") and f != INDEX)
    stems = {f[:-3] for f in notes}
    names = set()
    for f in notes:
        text = open(os.path.join(memdir, f), encoding="utf-8", errors="replace").read()
        fm = frontmatter(text)
        if fm is None:
            fail.append((f, "no frontmatter"))
        else:
            for key in ("name", "description", "type"):
                if not fm.get(key):
                    fail.append((f, "frontmatter has no %s" % key))
            if fm.get("name"):
                names.add(slug(fm["name"]))
                if slug(fm["name"]) != slug(f[:-3]):
                    fail.append((f, "name %r does not match the file" % fm["name"]))
        for target in WIKI.findall(text):
            if slug(target) not in {slug(s) for s in stems} | names:
                warn.append((f, "[[%s]] points to a note not yet written" % target))
        for n, line in enumerate(text.splitlines(), 1):
            if SECRET.search(line):
                fail.append((f, "line %d: a secret" % n))
            if RELATIVE.search(line):
                warn.append((f, "line %d: a relative date (%s): write the date" % (n, RELATIVE.search(line).group(0))))
    path = os.path.join(memdir, INDEX)
    if not os.path.isfile(path):
        return fail + [(INDEX, "the index is missing")], warn
    raw = open(path, "rb").read()
    lines = raw.decode("utf-8", "replace").splitlines()
    if len(lines) >= MAX_LINES or len(raw) >= MAX_BYTES:
        fail.append((INDEX, "%d lines, %d bytes: keep it under %d lines and %d bytes" % (len(lines), len(raw), MAX_LINES, MAX_BYTES)))
    seen = {}
    for n, line in enumerate(lines, 1):
        if len(line) > MAX_LINE:
            fail.append((INDEX, "line %d: %d characters, over %d" % (n, len(line), MAX_LINE)))
        if SECRET.search(line):
            fail.append((INDEX, "line %d: a secret" % n))
        for target in LINK.findall(line):
            seen[target] = seen.get(target, 0) + 1
            if target not in notes:
                fail.append((INDEX, "line %d: %s is not a note here" % (n, target)))
    for f in notes:
        if f not in seen:
            fail.append((f, "not in the index"))
        elif seen[f] > 1:
            fail.append((f, "in the index %d times" % seen[f]))
    return fail, warn


def report(memdir):
    fail, warn = check(memdir)
    for f, d in fail:
        print("FAIL %s: %s" % (f, d))
    for f, d in warn:
        print("warn %s: %s" % (f, d))
    print("memory gate: %s; %d failures, %d warnings" % (memdir, len(fail), len(warn)))
    return 1 if fail else 0


def selftest():
    import tempfile
    note = "---\nname: %s\ndescription: %s\ntype: project\n---\n\n%s\n"
    nested = "---\nname: %s\ndescription: %s\nmetadata:\n  type: feedback\n---\n\n%s\n"
    with tempfile.TemporaryDirectory() as t:
        def folder(files):
            d = tempfile.mkdtemp(dir=t)
            for f, text in files.items():
                open(os.path.join(d, f), "w").write(text)
            return d
        clean = {"MEMORY.md": "- [Build](build.md) — how to build\n- [Owner style](owner-style.md) — answers\n",
                 "build.md": note % ("build", "how to build", "Run `make build` (since 2026-09-01). See [[owner-style]]."),
                 "owner-style.md": nested % ("Owner style", "answers", "Short answers, the command first.")}
        assert check(folder(clean)) == ([], []), check(folder(clean))

        def fires(change, kind, words):
            files = dict(clean, **change)
            fail, warn = check(folder({k: v for k, v in files.items() if v is not None}))
            hits = fail if kind == "FAIL" else warn
            assert any(words in d for _, d in hits) and (kind == "warn" or fail), (change, fail, warn)
            if kind == "warn":
                assert not fail, (change, fail)
        fires({"build.md": "Run make build.\n"}, "FAIL", "no frontmatter")
        fires({"build.md": "---\nname: build\ntype: project\n---\nx\n"}, "FAIL", "no description")
        fires({"build.md": "---\nname: build\ndescription: d\n---\nx\n"}, "FAIL", "no type")
        fires({"build.md": note % ("Build steps", "d", "x")}, "FAIL", "does not match")
        fires({"MEMORY.md": "- [Build](build.md) — how to build\n"}, "FAIL", "not in the index")
        fires({"MEMORY.md": clean["MEMORY.md"] + "- [Build again](build.md) — dup\n"}, "FAIL", "2 times")
        fires({"MEMORY.md": clean["MEMORY.md"] + "- [Gone](gone.md) — old\n"}, "FAIL", "not a note here")
        fires({"MEMORY.md": clean["MEMORY.md"] + "- x\n" * 200}, "FAIL", "keep it under")
        fires({"MEMORY.md": clean["MEMORY.md"] + "- [Note](build.md) " + "x" * 30000 + "\n"}, "FAIL", "keep it under")
        fires({"MEMORY.md": clean["MEMORY.md"] + "- " + "y" * 160 + "\n"}, "FAIL", "over 150")
        fires({"build.md": note % ("build", "d", "Deploy with password: hunter2-real-one")}, "FAIL", "a secret")
        fires({"build.md": note % ("build", "d", "key ghp_" + "a" * 36)}, "FAIL", "a secret")
        fires({"build.md": note % ("build", "d", "See [[deploy-plan]].")}, "warn", "not yet written")
        fires({"build.md": note % ("build", "d", "The suite moved to make test last week.")}, "warn", "relative date")
        fires({"build.md": note % ("build", "d", "It broke 3 days ago.")}, "warn", "relative date")
        fires({"MEMORY.md": None}, "FAIL", "index is missing")
    print("memory gate selftest ok")


def main(argv):
    if argv[1:] == ["--selftest"]:
        return selftest()
    if len(argv) != 2 or not os.path.isdir(argv[1]):
        sys.exit(__doc__)
    sys.exit(report(argv[1]))


if __name__ == "__main__":
    main(sys.argv)
