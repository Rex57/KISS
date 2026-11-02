#!/usr/bin/env python3
"""The docs gate: are the repo's Markdown pages still clean? Standard library only.

    python3 -I check_docs.py [repo]       report, exit 1 on any failure
    python3 -I check_docs.py --selftest   plant each failure in a scratch repo and see it caught

The kiss-housekeeping skill keeps the master copy (its scripts/ folder). A repo runs its own
copy (tools/check_docs.py) with its CONFIG filled in. The code below CONFIG stays the same as
the master: the skill's Upkeep (U1) copies it over the project's copy and keeps its CONFIG.

The kind of a page comes from its path, so a script and a person read it the same way:
  history  under a history folder (archive/): not checked
  record   a path part starts with a date (YYYY-MM-DD): kept as written, linked from an index
  log      listed in CONFIG["logs"]: append-only, old entries keep their words
  agent    an agent or tool file (CLAUDE.md, .claude/...): links and names checked only
  living   everything else: kept true, has a status line, linked from the map
"""
import datetime, fnmatch, hashlib, importlib.util, os, re, subprocess, sys, tempfile, urllib.parse

CONFIG = {
    "map": "docs/README.md",             # routes every reader; links every living page
    "front_door": "README.md",           # links the map
    "history": ["archive/"],
    "logs": ["CHANGELOG.md", "docs/decisions.md"],
    "agent_files": ["CLAUDE.md", "*/CLAUDE.md", "AGENTS.md", "*/AGENTS.md", "GEMINI.md", "*/GEMINI.md",
                    ".claude/*", ".kiss/*"],
    "glossary": "docs/reference/glossary.md",   # its table with an "Old names" column feeds the names check
    "ignore": ["*node_modules/*"],
    "stale_days": 120,                   # a living page not reviewed for this long is a warning
}

TEST_CONFIG = {                          # the selftest's own: a project's filled-in CONFIG cannot break it
    "map": "docs/README.md", "front_door": "README.md", "history": ["archive/"],
    "logs": ["CHANGELOG.md", "docs/decisions.md"], "agent_files": ["CLAUDE.md", "*/CLAUDE.md", ".claude/*"],
    "glossary": "docs/reference/glossary.md", "ignore": [], "stale_days": 120,
}

# ---- shared reading (inventory.py and move_docs.py import these) ----------------------------

DATED = re.compile(r"^\d{4}-\d{2}-\d{2}")
LINK = re.compile(r"\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
FENCE = re.compile(r"^(```|~~~)[^\n]*\n.*?^\1[^\n]*$", re.S | re.M)
SPAN = re.compile(r"`[^`\n]+`")
STATUS = re.compile(r"^> Status: (current|draft|deprecated) · Owner: ([^·\n]+?) · Reviewed: (\d{4}-\d{2}-\d{2})\s*$", re.M)


def tracked(repo, *globs, config=CONFIG):
    """Files git tracks, plus new ones it does not ignore: the tree as the next commit will see it."""
    out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard", *(globs or ("*.md",))], cwd=repo,
                         capture_output=True, text=True, check=True).stdout.splitlines()
    return [p for p in out if os.path.isfile(os.path.join(repo, p))
            and not any(fnmatch.fnmatch(p, g) for g in config["ignore"])]


def use_project_config(repo):
    """A project's own gate (tools/check_docs.py) holds its CONFIG: use it here. CONFIG is updated in
    place, because tracked() and kind() bind it as their default argument."""
    path = os.path.join(repo, "tools", "check_docs.py")
    if os.path.isfile(path):
        spec = importlib.util.spec_from_file_location("project_check_docs", path)
        mod = importlib.util.module_from_spec(spec)
        sys.dont_write_bytecode = True          # a dry run leaves no __pycache__ in the project
        spec.loader.exec_module(mod)
        CONFIG.update(mod.CONFIG)


def kind(path, config=CONFIG):
    if any(path.startswith(h) for h in config["history"]):
        return "history"
    if any(fnmatch.fnmatch(path, p) for p in config["agent_files"]):
        return "agent"
    if path in config["logs"]:
        return "log"
    if any(DATED.match(part) for part in path.split("/")):
        return "record"
    return "living"


def blank_fences(text):
    return FENCE.sub(lambda m: "\n" * m.group(0).count("\n"), text)


def prose(text):
    """Fenced blocks and code spans blanked: identifiers in code are not prose."""
    return SPAN.sub(lambda m: " " * len(m.group(0)), blank_fences(text))


def links(path, text):
    """[(line, raw target, repo-relative path or None for a URL or an anchor)] of each inline link."""
    out = []
    for n, line in enumerate(blank_fences(text).splitlines(), 1):
        for m in LINK.finditer(line):
            raw = m.group(1)
            if re.match(r"^[a-zA-Z][\w+.-]*:", raw) or raw.startswith("#"):
                out.append((n, raw, None))
                continue
            target = raw.split("#", 1)[0].split("?", 1)[0]
            base = "" if target.startswith("/") else os.path.dirname(path)
            out.append((n, raw, os.path.normpath(os.path.join(base, target.lstrip("/")))))
    return out


def anchors(text):
    """The anchors a page offers: each heading's slug (a repeat gets -1, -2...), and each
    <a name=...> or id=. The slug: the heading's text, lower case, punctuation dropped, a space a hyphen."""
    out, seen = set(), {}
    for line in blank_fences(text).splitlines():
        m = re.match(r"^ {0,3}#{1,6}\s+(.*?)\s*#*\s*$", line)
        if m:
            h = re.sub(r"<[^>]+>", "", re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", m.group(1)))
            s = re.sub(r"[^\w\- ]", "", h.lower()).replace(" ", "-")
            out.add(s if s not in seen else "%s-%d" % (s, seen[s]))
            seen[s] = seen.get(s, 0) + 1
        out.update(re.findall(r"""<a\s+(?:name|id)=["']([^"']+)["']""", line))
    return out


def exists(target, every):
    """A path git has, or a folder that holds one: an empty folder left on disk does not count."""
    return target in every or any(f.startswith(target.rstrip("/") + "/") for f in every)


def old_names(repo, config=CONFIG):
    """[(current name, compiled pattern, as written)] from the glossary table's "Old names" column.
    A term written /like this/ is a regex; any other term matches as a whole word."""
    path = os.path.join(repo, config["glossary"])
    if not os.path.isfile(path):
        return []
    out, cols = [], None
    for line in open(path, encoding="utf-8"):
        row = line.strip()
        cells = ([c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", row[1:-1] if row.endswith("|") else row[1:])]
                 if row.startswith("|") else None)      # a \| inside a cell is a pipe, not a column
        if not cells:
            cols = None
            continue
        low = [c.lower() for c in cells]
        if "old names" in low:
            cols = (0, low.index("old names"))
            continue
        if cols is None or set(cells[0]) <= set("-: "):
            continue
        name = re.sub(r"[*`]", "", cells[cols[0]]).strip()
        for term in cells[cols[1]].split(","):          # so a regex term holds no comma
            term = term.strip().strip("`")
            if not term or term in ("-", "—"):
                continue
            rx = term[1:-1] if len(term) > 2 and term[0] == term[-1] == "/" else r"(?<![\w-])" + re.escape(term) + r"(?![\w-])"
            out.append((name, re.compile(rx), term))
    return out


# ---- the gate --------------------------------------------------------------------------------

def check(repo, config=CONFIG, today=None):
    """(failures, warnings, counts). Each failure is (check, path, detail)."""
    today = today or datetime.date.today()
    files = tracked(repo, config=config)
    every = set(tracked(repo, "*", config=config))
    kinds = {p: kind(p, config) for p in files}
    text = {p: open(os.path.join(repo, p), encoding="utf-8", errors="replace").read() for p in files}
    fail, warn = [], []
    linked_from = {p: set() for p in files}

    slugs = {}
    for p in files:
        for n, raw, target in links(p, text[p]):
            frag = raw.split("#", 1)[1] if "#" in raw and not re.match(r"^[a-zA-Z][\w+.-]*:", raw) else ""
            dest = p if raw.startswith("#") else target
            if frag and kinds[p] in ("living", "log", "agent") and dest in text:   # a Markdown page we read
                if dest not in slugs:
                    slugs[dest] = anchors(text[dest])
                if urllib.parse.unquote(frag).lower() not in slugs[dest]:
                    fail.append(("anchor", p, "line %d: %s: %s has no heading with that anchor" % (n, raw, dest)))
            if target is None:
                continue
            for t in (target, os.path.join(target, "README.md")):   # a folder link reaches its README
                if t in linked_from:
                    linked_from[t].add(p)
            if kinds[p] != "history" and kinds[p] != "record" and not exists(target, every):
                fail.append(("link", p, "line %d: %s does not exist" % (n, raw)))

    for p, k in kinds.items():
        if k in ("living", "log"):
            m = STATUS.search("\n".join(text[p].splitlines()[:12]))
            if not m:
                fail.append(("status", p, "no status line in the first 12 lines: "
                                          "'> Status: current · Owner: <name> · Reviewed: YYYY-MM-DD'"))
            else:
                age = (today - datetime.date.fromisoformat(m.group(3))).days
                if age > config["stale_days"]:
                    warn.append(("stale", p, "reviewed %s, %d days ago" % (m.group(3), age)))
            if p != config["map"] and config["map"] not in linked_from[p]:
                fail.append(("map", p, "the map (%s) does not link it" % config["map"]))
        if k == "record" and not any(kinds.get(q) in ("living", "log", "agent", "record") for q in linked_from[p]):
            fail.append(("index", p, "no living page, log or record links it: add it to its index"))
    if config["map"] not in kinds:
        fail.append(("map", config["map"], "the map is missing"))
    elif config["front_door"] in kinds and config["front_door"] not in linked_from[config["map"]]:
        fail.append(("map", config["front_door"], "the front door does not link the map"))

    names = old_names(repo, config)
    for p, k in kinds.items():
        if k not in ("living", "agent") or p == config["glossary"]:
            continue
        for n, line in enumerate(prose(text[p]).splitlines(), 1):
            for name, rx, term in names:
                if rx.search(line) and name not in line:
                    fail.append(("name", p, "line %d: '%s' is an old name of %s" % (n, term, name)))

    seen = {}
    for p in files:
        if kinds[p] == "history":
            continue
        h = hashlib.sha1(text[p].encode()).hexdigest()
        if h in seen:
            fail.append(("copy", p, "same bytes as %s" % seen[h]))
        seen.setdefault(h, p)

    counts = {k: sum(1 for v in kinds.values() if v == k) for k in ("living", "log", "agent", "record", "history")}
    return fail, warn, counts


def report(repo, config=CONFIG):
    fail, warn, counts = check(repo, config)
    for c, p, d in fail:
        print("FAIL %-6s %s: %s" % (c, p, d))
    for c, p, d in warn:
        print("warn %-6s %s: %s" % (c, p, d))
    total = sum(counts.values())
    print("docs gate: %d pages (%s); %d failures, %d warnings"
          % (total, ", ".join("%d %s" % (v, k) for k, v in counts.items()), len(fail), len(warn)))
    return 1 if fail else 0


def selftest(copy=True):
    """Each check fires on its planted fault and stays quiet on the clean tree; a copy with its
    CONFIG filled in passes the same selftest."""
    def run(files, **cfg):
        with tempfile.TemporaryDirectory() as d:
            for p, body in files.items():
                os.makedirs(os.path.join(d, os.path.dirname(p)), exist_ok=True)
                open(os.path.join(d, p), "w", encoding="utf-8").write(body)
            subprocess.run(["git", "init", "-q"], cwd=d, check=True)
            subprocess.run(["git", "add", "-A"], cwd=d, check=True)
            return check(d, dict(TEST_CONFIG, **cfg), today=datetime.date(2026, 11, 2))

    ok = "> Status: current · Owner: Ana · Reviewed: 2026-11-01\n"
    clean = {
        "README.md": "# R\n" + ok + "[map](docs/README.md)\n",
        "docs/README.md": "# Map\n" + ok + "[front](../README.md) [a](a.md) [g](reference/glossary.md) [log](decisions.md)\n",
        "docs/a.md": "# A\n" + ok + "Quillo, called Fernweb before. See [r](design/2026-10-01-r.md). `fernweb` is an id.\n"
                     "[here](#a) [log](decisions.md#d-the-log) [again](decisions.md#d-the-log-1)\n",
        "docs/decisions.md": "# D\n" + ok + "1. Fernweb was chosen.\n## D: the log\n## D: the `log`\n",
        "docs/design/2026-10-01-r.md": "# R\nFernweb, kept as written. [gone](nowhere.md)\n",
        "docs/reference/glossary.md": "# G\n" + ok + "| Name | Means | Old names |\n|---|---|---|\n| Quillo | the reader app | Fernweb, /\\bV1\\b/ |\n| V2-Next | the new store | /\\bV2\\b(?!-Next\\| framework)/ |\n",
        "archive/old.md": "# Old\n[gone](nowhere.md) Fernweb\n",
        "CLAUDE.md": "# Agent\nUse Quillo.\n",
    }
    fail, warn, counts = run(clean)
    assert not fail and not warn, (fail, warn)
    assert counts == {"living": 4, "log": 1, "agent": 1, "record": 1, "history": 1}, counts
    planted = {
        "link": {"docs/a.md": clean["docs/a.md"] + "[x](missing.md)\n"},
        "status": {"docs/a.md": "# A\nno line\n[r](design/2026-10-01-r.md)\n"},
        "map": {"docs/b.md": "# B\n" + ok},
        "index": {"docs/design/2026-10-02-s.md": "# S\n"},
        "index ": {"docs/design/2026-10-04-f/README.md": "# F\n"},
        "name": {"docs/a.md": clean["docs/a.md"] + "The Fernweb plugin.\n"},
        "copy": {"docs/design/2026-10-03-t.md": clean["docs/design/2026-10-01-r.md"]},
        "anchor": {"docs/a.md": clean["docs/a.md"] + "[x](decisions.md#gone)\n"},
    }
    for check_name, change in planted.items():
        fail, _, _ = run(dict(clean, **change))
        assert any(c == check_name.strip() for c, _, _ in fail), (check_name, fail)
    os_dir_fail, _, _ = run(dict(clean, **{"docs/a.md": clean["docs/a.md"] + "[e](gone/)\n", "docs/gone/.keep": ""}))
    assert not any(c == "link" for c, _, _ in os_dir_fail), os_dir_fail     # a folder git tracks a file in
    assert not exists("docs/empty", {"docs/a.md"}) and exists("docs", {"docs/a.md"})   # an empty folder on disk is gone
    fail, _, _ = run(dict(clean, **{"docs/design/2026-10-04-f/README.md": "# F\n",
                                    "docs/a.md": clean["docs/a.md"] + "[f](design/2026-10-04-f/)\n"}))
    assert not fail, fail                                # a link to a folder indexes its README
    _, warn, _ = run(dict(clean, **{"docs/a.md": clean["docs/a.md"].replace("2026-11-01", "2026-01-01")}))
    assert [c for c, _, _ in warn] == ["stale"], warn
    fail, _, _ = run(dict(clean, **{"CLAUDE.md": "# Agent\nThe V1 console.\n"}))
    assert any(c == "name" and p == "CLAUDE.md" for c, p, _ in fail), fail
    fail, _, _ = run(dict(clean, **{"CLAUDE.md": "# Agent\nThe V2 framework, and V2-Next.\n"}))
    assert not fail, fail                                # an escaped pipe in a pattern is alternation
    fail, _, _ = run(dict(clean, **{"CLAUDE.md": "# Agent\nThe V2 console.\n"}))
    assert any(c == "name" for c, _, _ in fail), fail
    fail, _, _ = run(dict(clean, **{"README.md": "# R\n" + ok}))
    assert any(c == "map" and p == "README.md" for c, p, _ in fail), fail    # the map links the front door too
    if copy:
        with tempfile.TemporaryDirectory() as d:
            src = open(os.path.abspath(__file__), encoding="utf-8").read()
            filled = re.sub(r"(?ms)^CONFIG = \{.*?^\}", lambda m: 'CONFIG = {"map": "docs/index.md", "front_door": "README.md", '
                            '"history": ["docs/archive/"], "logs": ["CHANGELOG.md"], "agent_files": [], '
                            '"glossary": "docs/glossary.md", "ignore": [], "stale_days": 30}', src, count=1)
            assert filled != src
            open(os.path.join(d, "check_docs.py"), "w", encoding="utf-8").write(filled)
            out = subprocess.run([sys.executable, "-I", os.path.join(d, "check_docs.py"), "--selftest", "--no-copy"],
                                 capture_output=True, text=True)
            assert out.returncode == 0, "a copy with a filled CONFIG fails its selftest:\n" + out.stderr
    return "check_docs selftest ok: 7 checks fire on their planted fault, quiet on a clean tree"


if __name__ == "__main__":
    if sys.argv[1:2] == ["--selftest"]:
        print(selftest(copy="--no-copy" not in sys.argv))
    elif sys.argv[1:2] and sys.argv[1].startswith("-"):
        sys.exit(__doc__)
    else:
        sys.exit(report(sys.argv[1] if len(sys.argv) > 1 else "."))
